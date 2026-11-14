"""Opt-in process containment. This is not a hardware overheat interlock.

Providers are trusted installed Python callables, not untrusted sandboxed code.
The original cooperative TemperatureGuard remains available unchanged.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time

from .thermal import TemperatureGuard


def _positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(name + ' must be finite and positive')
    return float(value)


def _group_exists(pid):
    """An extant (even zombie-only) owned group is not confirmed quiescent."""
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass  # Cannot confirm cleanup; do not report success.
    return True


def _stop(process, grace):
    """Bounded cleanup; report failure instead of waiting forever in unkillable I/O."""
    signal_failed = False
    def send(sig):
        nonlocal signal_failed
        try:
            if os.name == 'posix':
                os.killpg(process.pid, sig)
            elif process.poll() is None:
                process.terminate() if sig == signal.SIGTERM else process.kill()
        except ProcessLookupError:
            pass
        except OSError:
            signal_failed = True
    send(signal.SIGTERM)
    try:
        out, err = process.communicate(timeout=grace)
    except subprocess.TimeoutExpired:
        out = err = None
    # A descendant can ignore TERM after the direct child exits. Kill this
    # owned POSIX session even if communicate has already returned.
    send(signal.SIGKILL if hasattr(signal, 'SIGKILL') else signal.SIGTERM)
    if out is None:
        try:
            out, err = process.communicate(timeout=grace)
        except subprocess.TimeoutExpired:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
            return b'', b'', 'fail'
    if os.name == 'posix':
        deadline = time.monotonic() + grace
        while _group_exists(process.pid):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return out, err, 'fail'
            time.sleep(min(.01, remaining))
    return out, err, 'pass' if process.poll() is not None and not signal_failed else 'fail'


def run_supervised(command, *, timeout_seconds, cleanup_seconds=0.25,
                   input_bytes=None, env=None, cwd=None):
    """Run an explicitly supplied argv in a separate process with a wall deadline.

    POSIX uses a new session and TERM/KILL for the owned process group,
    including descendants left behind after the direct child exits normally.
    Windows contains only the direct child; no Job Object/tree-cleanup claim.
    A timeout is failure even if a late process emits an apparent success.
    """
    timeout = _positive(timeout_seconds, 'timeout_seconds')
    grace = _positive(cleanup_seconds, 'cleanup_seconds')
    if (not isinstance(command, (tuple, list)) or not command
            or not all(isinstance(s, str) and s and '\0' not in s for s in command)):
        raise ValueError('command must be a nonempty argv list; no shell')
    if input_bytes is not None and not isinstance(input_bytes, bytes):
        raise TypeError('input_bytes must be bytes')
    started = time.monotonic()
    p = subprocess.Popen(command, stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         start_new_session=os.name == 'posix', env=env, cwd=cwd)
    timed_out = False
    try:
        try:
            out, err = p.communicate(input=input_bytes, timeout=max(.001, timeout-(time.monotonic()-started)))
            cleanup = 'not_applicable'
            if os.name == 'posix' and _group_exists(p.pid):
                out, err, cleanup = _stop(p, grace)
        except subprocess.TimeoutExpired:
            timed_out = True
            out, err, cleanup = _stop(p, grace)
    except BaseException:
        _stop(p, grace)
        raise
    finally:
        # communicate() can leave stdin open when it is interrupted while
        # writing a large request. Each parent-owned pipe must close on all paths.
        for stream in (p.stdin, p.stdout, p.stderr):
            if stream is not None:
                stream.close()
    return {'pid': p.pid, 'timed_out': timed_out, 'exit_code': p.returncode, 'cleanup': cleanup,
            'elapsed_seconds': time.monotonic()-started, 'stdout': out, 'stderr': err,
            'scope': 'POSIX owned process group' if os.name == 'posix' else 'direct child only'}


class IsolatedIOError(OSError):
    def __init__(self, message, receipt):
        self.receipt = receipt
        super().__init__(message)


class _Operations:
    def __init__(self, timeout, cleanup):
        self.timeout = _positive(timeout, 'io_timeout_seconds')
        self.cleanup = _positive(cleanup, 'cleanup_seconds')
        self.receipts = []
        self.failed = False

    def call(self, action, **fields):
        if self.failed:
            raise IsolatedIOError('I/O transport is latched after a failed operation', self.receipts[-1])
        nonce = secrets.token_hex(16)
        request = {'schema_version': 1, 'nonce': nonce, 'action': action, **fields}
        raw = json.dumps(request, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        if len(raw) > 8 * 1024 * 1024:
            raise ValueError('isolated I/O request exceeds 8 MiB')
        # Propagate the caller's installed/test module search paths without
        # putting provider data, checkpoint contents or credentials in argv.
        child_env = os.environ.copy()
        child_env['PYTHONPATH'] = os.pathsep.join(str(Path(p or '.').resolve()) for p in sys.path)
        worker = str(Path(__file__).with_name('_io_worker.py'))
        result = run_supervised([sys.executable, '-u', worker], input_bytes=raw,
                                timeout_seconds=self.timeout, cleanup_seconds=self.cleanup, env=child_env)
        receipt = {k: v for k, v in result.items() if k not in ('stdout', 'stderr')}
        receipt.update(action=action, request_sha256=hashlib.sha256(raw).hexdigest(),
                       stderr=result['stderr'].decode('utf-8', 'replace')[-4096:])
        self.receipts.append(receipt)
        # Bound retained metadata; caller can drain/export receipts between polls.
        del self.receipts[:-128]
        try:
            if result['timed_out'] or result['exit_code'] != 0 or result['cleanup'] == 'fail':
                raise ValueError('worker timeout, nonzero exit or unconfirmed cleanup')
            if len(result['stdout']) > 8 * 1024 * 1024:
                raise ValueError('worker response exceeds 8 MiB')
            response = json.loads(result['stdout'])
            if (not isinstance(response, dict) or type(response.get('schema_version')) is not int
                    or response.get('schema_version') != 1 or response.get('nonce') != nonce
                    or response.get('action') != action or response.get('request_sha256') != receipt['request_sha256']
                    or response.get('ok') is not True):
                raise ValueError('worker receipt identity/status mismatch')
            value = response['value']
            if (action == 'exists' and type(value) is not bool
                    or action == 'load' and not isinstance(value, dict)
                    or action == 'read' and not isinstance(value, list)
                    or action == 'commit' and value not in ('FILE_AND_DIRECTORY_FSYNC_COMPLETED', 'FILE_FSYNC_ONLY')):
                raise ValueError('worker result type/durability mismatch')
            return value
        except (ValueError, KeyError, TypeError) as exc:
            self.failed = True
            receipt['error'] = str(exc)
            raise IsolatedIOError('isolated ' + action + ' failed; no success/durability is inferred', receipt) from exc


class _ProcessCheckpointStore:
    def __init__(self, path, operations, store_spec):
        # Parent performs no filesystem probe/mkdir/read/fsync in this adapter.
        self.path = Path(os.path.abspath(os.fspath(path)))
        self.operations, self.store_spec = operations, store_spec

    def _call(self, action, **fields):
        return self.operations.call(action, path=str(self.path), store_spec=self.store_spec, **fields)

    def exists(self):
        return self._call('exists')

    def load(self):
        return self._call('load')

    def commit(self, payload):
        # The request digest binds nonce, generation, complete payload and path.
        return self._call('commit', payload=payload)


class IsolatedTemperatureGuard(TemperatureGuard):
    """Opt-in guard whose reader and checkpoint operations run in disposable children.

    Use an importable ``module:callable`` reader, with JSON keyword arguments.
    Lambdas/live parent state are deliberately unsupported. Each call is a fresh
    process. No Python callable, NumPy tensor or native pointer crosses IPC.
    Blocking I/O no longer traps the parent in an unbounded reader/fsync call.
    GIL-held native computation in this parent still requires an outer supervisor.
    """
    def __init__(self, checkpoint, *, reader_spec='thermal:read_linux_cpu_temperatures',
                 reader_kwargs=None, io_timeout_seconds=2.0, cleanup_seconds=0.25,
                 checkpoint_store_spec='thermal:CheckpointStore', **kwargs):
        if 'reader' in kwargs:
            raise ValueError('use an importable reader_spec, not a parent-process reader')
        self.reader_spec, self.reader_kwargs = reader_spec, dict(reader_kwargs or {})
        self.reader_operations = _Operations(io_timeout_seconds, cleanup_seconds)
        self.checkpoint_operations = _Operations(io_timeout_seconds, cleanup_seconds)
        self.checkpoint_store_spec = checkpoint_store_spec
        super().__init__(checkpoint, reader=self._read, **kwargs)

    def _make_store(self, checkpoint):
        return _ProcessCheckpointStore(checkpoint, self.checkpoint_operations, self.checkpoint_store_spec)

    def _read(self):
        return self.reader_operations.call('read', reader_spec=self.reader_spec, reader_kwargs=self.reader_kwargs)

    def _report(self):
        report = super()._report()
        report['io_isolation'] = 'disposable subprocesses; cooperative parent guard'
        report['last_reader_receipt'] = self.reader_operations.receipts[-1] if self.reader_operations.receipts else None
        report['last_checkpoint_receipt'] = self.checkpoint_operations.receipts[-1] if self.checkpoint_operations.receipts else None
        return report
