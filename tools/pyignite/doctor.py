"""Run the native smoke executable in a bounded child; never import NumPy.

Exit 0 means this smoke passed, not hardware health or full framework support.
Reported hardware events are caller-supplied observations, not sensor readings.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import signal
import subprocess
import tempfile

EVENTS = ('corrected-error', 'uncorrected-error', 'thermal-alarm', 'data-mismatch')


def event_policy(events):
    events = set(events)
    if events - set(EVENTS):
        raise ValueError('unknown hardware event')
    if events & {'uncorrected-error', 'data-mismatch'}:
        return 'QUARANTINE'
    if 'thermal-alarm' in events:
        return 'STOP_AND_COOL'
    if 'corrected-error' in events:
        return 'REVIEW_REQUIRED'
    return 'UNKNOWN'


def run_probe(command, *, timeout=10):
    """Run a trusted probe command, killing its process group on timeout (POSIX)."""
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('timeout must be positive and finite')
    env = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
               MKL_NUM_THREADS='1', VECLIB_MAXIMUM_THREADS='1')
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            process = subprocess.Popen(command, stdout=out, stderr=err, env=env,
                                       start_new_session=(os.name == 'posix'))
        except OSError as exc:
            return {'status': 'START_FAILED', 'detail': str(exc)}
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == 'posix':
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                process.kill()
            process.wait()
            return {'status': 'TIMEOUT', 'returncode': process.returncode}
        out.seek(0)
        err.seek(0)
        raw = out.read(8193)
        result = {'returncode': process.returncode,
                  'stderr': err.read(4096).decode('utf-8', errors='replace')}
        if process.returncode:
            result['status'] = 'CRASH' if process.returncode < 0 else 'FAILED'
            if process.returncode < 0:
                result['signal'] = -process.returncode
            return result
        try:
            payload = json.loads(raw) if len(raw) <= 8192 else None
        except (ValueError, UnicodeDecodeError):
            payload = None
        valid = (isinstance(payload, dict) and payload.get('schema_version') == 1
                 and payload.get('status') == 'PASS' and payload.get('checks') == 7
                 and payload.get('pointer_bits') in (32, 64)
                 and payload.get('scope') == 'native_core_smoke_only')
        result.update(status='PASS' if valid else 'INVALID_REPORT', payload=payload)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=10)
    parser.add_argument('--qemu-cpu', help='explicit qemu-i386 CPU model; records emulation')
    parser.add_argument('--qemu-root', type=Path, help='target loader/library root for qemu-i386')
    parser.add_argument('--event', action='append', choices=EVENTS, default=[])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error('--timeout must be positive and finite')
    if args.qemu_root and not args.qemu_cpu:
        parser.error('--qemu-root requires --qemu-cpu')
    binary = args.binary.resolve()
    policy = event_policy(args.event)
    command = [str(binary)]
    if args.qemu_cpu:
        command = ['qemu-i386', '-cpu', args.qemu_cpu]
        if args.qemu_root:
            command += ['-L', str(args.qemu_root.resolve())]
        command.append(str(binary))
    report = {
        'schema_version': 1,
        'execution': 'EMULATED' if args.qemu_cpu else 'LOCAL',
        'host': {'system': platform.system(), 'machine': platform.machine()},
        'command': command, 'health': policy,
        'events': args.event, 'event_source': 'caller_supplied_not_auto_detected',
        'coverage': 'tiny native core smoke; no cache diagnosis, no full Python/NumPy validation',
        'legacy_hardware_certification': 'NOT_ASSESSED',
    }
    if policy != 'UNKNOWN':
        report['probe'] = {'status': 'NOT_RUN', 'reason': 'resolve reported hardware event first'}
        report['action'] = policy
    else:
        try:
            before = hashlib.sha256(binary.read_bytes()).hexdigest()
            report['probe'] = run_probe(command, timeout=args.timeout)
            after = hashlib.sha256(binary.read_bytes()).hexdigest()
            report['binary_sha256'] = before
            if before != after:
                report['probe']['status'] = 'BINARY_CHANGED'
        except OSError as exc:
            report['probe'] = {'status': 'START_FAILED', 'detail': str(exc)}
        report['action'] = ('SMOKE_PASS_HEALTH_UNKNOWN'
                            if report['probe']['status'] == 'PASS' else 'STOP')
    text = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(text, end='')
    return 0 if report['action'] == 'SMOKE_PASS_HEALTH_UNKNOWN' else 2


if __name__ == '__main__':
    raise SystemExit(main())
