# SPDX-License-Identifier: Apache-2.0
"""Bounded POSIX subprocess experiment, not a security or hardware sandbox."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import struct
import subprocess
import sys
import threading
import time
import uuid

from .radix_portability import (
    BinaryIntegerBackend, BalancedTernaryBackend, ContractError, EncodedRequest,
    EncodedResult, WordFormat, MAX_ITEMS, SCHEMA_VERSION, _admit, _output_format,
)

WIRE_VERSION = 1
MAX_FRAME = 256 * 1024
MAX_RESPONSE = 32 * 1024
MAX_STDERR = 8192
MAX_IDS = 4096
MAX_TTL_NS = 60_000_000_000
ROOT = Path(__file__).resolve().parents[1]
HEX_ID = re.compile(r'[0-9a-f]{32}\Z')


class IPCFailure(RuntimeError):
    """An explicit failed attempt. No oracle value or partial result is returned."""
    def __init__(self, code, message, details=None):
        super().__init__(f'{code}: {message}')
        self.code = code
        self.details = details or {}


def canonical(data):
    return json.dumps(data, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def digest(data):
    return hashlib.sha256(canonical(data)).hexdigest()


def fields(data, names):
    if type(data) is not dict or set(data) != set(names.split()):
        raise ContractError('unexpected object fields')


def integer(value, minimum=0, maximum=None):
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise ContractError('integer outside protocol bounds')
    return value


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError('duplicate JSON key')
        result[key] = value
    return result


def _constant(value):
    raise ContractError('nonfinite JSON number')


def pack(data, limit=MAX_FRAME):
    raw = canonical(data)
    if not 0 < len(raw) <= limit:
        raise ContractError('frame exceeds byte limit')
    return struct.pack('!I', len(raw)) + raw


def unpack(raw, limit=MAX_FRAME):
    if len(raw) < 4:
        raise ContractError('truncated frame header')
    length = struct.unpack('!I', raw[:4])[0]
    if not 0 < length <= limit or len(raw) != length + 4:
        raise ContractError('invalid frame length or trailing frame/data')
    # Reject excessive nesting before invoking either JSON parser or serializer.
    depth, quoted, escaped = 0, False, False
    for byte in raw[4:]:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            if depth > 12:
                raise ContractError('JSON nesting exceeds limit')
        elif byte in (93, 125):
            depth -= 1
    try:
        data = json.loads(raw[4:].decode('utf-8'), object_pairs_hook=_pairs,
                          parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ContractError('malformed JSON frame') from exc
    if canonical(data) != raw[4:]:
        raise ContractError('wire JSON is not canonical')
    return data


def backend_for(name, width=None):
    if name == 'binary':
        return BinaryIntegerBackend(32 if width is None else width)
    if name == 'ternary':
        return BalancedTernaryBackend(21 if width is None else width)
    raise ContractError('unsupported backend')


def parse_format(data):
    fields(data, 'encoding width')
    return WordFormat(data['encoding'], data['width'])


def parse_request(data, now_ns=None):
    fields(data, 'wire_version kind request_id issued_unix_ns expires_unix_ns backend payload payload_sha256')
    if integer(data['wire_version']) != WIRE_VERSION or data['kind'] != 'integer_dot':
        raise ContractError('unsupported wire version or operation')
    if type(data['request_id']) is not str or not HEX_ID.fullmatch(data['request_id']):
        raise ContractError('invalid request ID')
    issued = integer(data['issued_unix_ns'])
    expires = integer(data['expires_unix_ns'])
    now = time.time_ns() if now_ns is None else now_ns
    if not issued <= now < expires or not 0 < expires - issued <= MAX_TTL_NS:
        raise ContractError('expired request or invalid lifetime')
    payload = data['payload']
    fields(payload, 'schema_version format lhs rhs')
    fmt = parse_format(payload['format'])
    backend = backend_for(data['backend'], fmt.width)
    vectors = []
    for key in ('lhs', 'rhs'):
        vector = payload[key]
        if type(vector) is not list or not 1 <= len(vector) <= MAX_ITEMS:
            raise ContractError('invalid vector')
        if any(type(word) is not list for word in vector):
            raise ContractError('invalid word array')
        vectors.append(tuple(tuple(word) for word in vector))
    request = EncodedRequest(payload['schema_version'], fmt, *vectors)
    _admit(request, backend.capabilities)
    if data['payload_sha256'] != request.sha256:
        raise ContractError('request payload digest mismatch')
    return request, backend


def parse_result(data, request):
    fields(data, 'schema_version request_sha256 format digits')
    if integer(data['schema_version']) != SCHEMA_VERSION or data['request_sha256'] != request.sha256:
        raise ContractError('stale result identity or schema')
    fmt = parse_format(data['format'])
    if fmt != _output_format(request) or type(data['digits']) is not list:
        raise ContractError('incorrect result format')
    result = EncodedResult(SCHEMA_VERSION, data['request_sha256'], fmt, tuple(data['digits']))
    fmt.validate_digits(result.digits)
    return result


def _signal_group(process, sig, events):
    try:
        os.killpg(process.pid, sig)
        events.append(signal.Signals(sig).name)
    except ProcessLookupError:
        pass


def _cleanup(process, failed):
    events = []
    if failed:
        _signal_group(process, signal.SIGTERM, events)
        try:
            process.wait(timeout=0.15)
        except subprocess.TimeoutExpired:
            pass
    # Also remove any descendants still in our group after the leader exits.
    _signal_group(process, signal.SIGKILL, events)
    try:
        process.wait(timeout=0.5)
        reaped = True
    except subprocess.TimeoutExpired:
        reaped = False
    for stream in (process.stdin, process.stdout, process.stderr):
        stream.close()
    return {'signals': events, 'reaped': reaped, 'returncode': process.returncode}


def exchange(command, raw, deadline_ns):
    """Multiplex all three pipes; cap stored bytes while reading, not afterwards."""
    if sys.platform not in ('linux', 'darwin'):
        raise IPCFailure('UNSUPPORTED_OS', 'Linux and macOS only')
    started = time.monotonic_ns()
    if started >= deadline_ns:
        raise IPCFailure('TIMEOUT', 'deadline elapsed before spawn')
    try:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, bufsize=0, start_new_session=True,
                                   close_fds=True, cwd=ROOT,
                                   env={'PATH': os.defpath, 'LANG': 'C', 'LC_ALL': 'C'})
    except OSError as exc:
        raise IPCFailure('SPAWN_FAILED', str(exc)) from exc
    spawned = time.monotonic_ns()
    out, err = bytearray(), bytearray()
    sent = 0
    marks = {'spawn_ns': spawned - started, 'write_syscalls_ns': 0, 'read_syscalls_ns': 0,
             'request_send_start_ns': None, 'response_received_ns': None}
    failure = None
    try:
        with selectors.DefaultSelector() as selector:
            for stream, event in ((process.stdin, selectors.EVENT_WRITE),
                                  (process.stdout, selectors.EVENT_READ),
                                  (process.stderr, selectors.EVENT_READ)):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, event)
            while selector.get_map() or process.poll() is None:
                remaining = (deadline_ns - time.monotonic_ns()) / 1e9
                if remaining <= 0:
                    raise IPCFailure('TIMEOUT', 'worker exceeded deadline')
                if not selector.get_map():
                    try:
                        process.wait(timeout=remaining)
                    except subprocess.TimeoutExpired as exc:
                        raise IPCFailure('TIMEOUT', 'worker closed pipes but did not exit') from exc
                    break
                for key, _ in selector.select(min(remaining, 0.05)):
                    stream = key.fileobj
                    begin = time.monotonic_ns()
                    if stream is process.stdin:
                        if marks['request_send_start_ns'] is None:
                            marks['request_send_start_ns'] = begin
                        try:
                            sent += os.write(stream.fileno(), raw[sent:sent + 4096])
                        except BlockingIOError:
                            continue
                        except BrokenPipeError:
                            selector.unregister(stream)
                            stream.close()
                            continue
                        marks['write_syscalls_ns'] += time.monotonic_ns() - begin
                        if sent == len(raw):
                            selector.unregister(stream)
                            stream.close()
                    else:
                        target, cap = (out, MAX_RESPONSE + 4) if stream is process.stdout else (err, MAX_STDERR)
                        try:
                            block = os.read(stream.fileno(), min(4096, cap - len(target) + 1))
                        except BlockingIOError:
                            continue
                        marks['read_syscalls_ns'] += time.monotonic_ns() - begin
                        if not block:
                            selector.unregister(stream)
                        else:
                            target.extend(block)
                            if stream is process.stdout:
                                marks['response_received_ns'] = time.monotonic_ns()
                            if len(target) > cap:
                                raise IPCFailure('OUTPUT_LIMIT', 'worker output exceeded byte limit')
                            if stream is process.stdout and len(out) >= 4:
                                length = struct.unpack('!I', out[:4])[0]
                                if not 0 < length <= MAX_RESPONSE or len(out) > length + 4:
                                    raise IPCFailure('BAD_FRAME', 'oversized or repeated response frame')
            if time.monotonic_ns() >= deadline_ns:
                raise IPCFailure('TIMEOUT', 'worker completed after deadline')
            if process.returncode != 0:
                raise IPCFailure('EXIT', f'worker exit status {process.returncode}')
            if sent != len(raw):
                raise IPCFailure('INCOMPLETE_SEND', 'worker did not receive full request')
    except BaseException as exc:
        failure = exc
    finally:
        cleanup_start = time.monotonic_ns()
        cleanup = _cleanup(process, failure is not None)
        marks['cleanup_ns'] = time.monotonic_ns() - cleanup_start
        marks['exchange_wall_ns'] = cleanup_start - spawned
    details = {'pid': process.pid, **cleanup, 'stderr': bytes(err).decode('utf-8', errors='replace'),
               'timing_ns': marks}
    if not cleanup['reaped']:
        raise IPCFailure('CLEANUP_FAILED', 'worker could not be reaped within cleanup budget', details)
    if failure is not None:
        if isinstance(failure, IPCFailure):
            failure.details.update(details)
        raise failure
    return bytes(out), details


class SubprocessDotClient:
    """Serial session; IDs (including failed attempts) cannot be reused in this object.

    The ledger is bounded and never evicts. A new client starts a new ledger; this
    is not durable/global exactly-once execution. Custom commands are trusted code.
    """
    def __init__(self, *, _command=None):
        self._seen = set()
        self._lock = threading.Lock()
        self._command = _command or [sys.executable, '-I', '-S', str(ROOT / 'motionbricks/radix_worker.py')]

    def run(self, lhs, rhs, backend='binary', *, width=None, timeout_s=5.0, request_id=None):
        with self._lock:
            return self._run(lhs, rhs, backend, width, timeout_s, request_id)

    def _run(self, lhs, rhs, name, width, timeout_s, request_id):
        start = time.monotonic_ns()
        if type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not 0.01 <= timeout_s <= 60:
            raise ContractError('timeout must be finite, in [0.01,60] seconds')
        deadline = start + int(timeout_s * 1e9)
        backend = backend_for(name, width)
        fmt = backend.capabilities.input_format
        if type(lhs) not in (tuple, list) or type(rhs) not in (tuple, list):
            raise ContractError('integer lists/tuples required')
        if not 1 <= len(lhs) == len(rhs) <= MAX_ITEMS:
            raise ContractError('invalid operand count')
        lhs, rhs = tuple(lhs), tuple(rhs)
        low, high = fmt.bounds
        if any(type(v) is not int or not low <= v <= high for v in lhs + rhs):
            raise ContractError('invalid or out-of-range operand')
        rid = uuid.uuid4().hex if request_id is None else request_id
        if type(rid) is not str or not HEX_ID.fullmatch(rid):
            raise ContractError('request_id must be 32 lowercase hexadecimal digits')
        if rid in self._seen:
            raise IPCFailure('DUPLICATE_ID', 'attempt ID already used in this client')
        if len(self._seen) >= MAX_IDS:
            raise IPCFailure('LEDGER_FULL', 'create a new explicitly scoped client session')
        self._seen.add(rid)
        validated = time.monotonic_ns()
        request = EncodedRequest(SCHEMA_VERSION, fmt, tuple(fmt.encode(v) for v in lhs),
                                 tuple(fmt.encode(v) for v in rhs))
        encoded = time.monotonic_ns()
        issued = time.time_ns()
        envelope = {'wire_version': WIRE_VERSION, 'kind': 'integer_dot', 'request_id': rid,
                    'issued_unix_ns': issued, 'expires_unix_ns': issued + deadline - encoded,
                    'backend': name, 'payload': asdict(request), 'payload_sha256': request.sha256}
        raw = pack(envelope)
        envelope_hash = digest(envelope)
        serialized = time.monotonic_ns()
        response_raw, process = exchange(self._command, raw, deadline)
        received = time.monotonic_ns()
        try:
            response = unpack(response_raw, MAX_RESPONSE)
            fields(response, 'wire_version request_id request_sha256 status result result_sha256 timing_ns')
            if integer(response['wire_version']) != WIRE_VERSION:
                raise ContractError('unsupported response version')
            if response['request_id'] != rid or response['request_sha256'] != envelope_hash:
                raise ContractError('stale response identity')
            if response['status'] != 'OK':
                raise ContractError('worker did not return OK')
            if response['result_sha256'] != digest(response['result']):
                raise ContractError('result digest mismatch')
            result = parse_result(response['result'], request)
            timing = response['timing_ns']
            fields(timing, 'request_received_ns response_ready_ns decode_request_ns backend_execute_ns encode_result_ns')
            for value in timing.values():
                integer(value)
            send = process['timing_ns']['request_send_start_ns']
            arrival = process['timing_ns']['response_received_ns']
            if not send <= timing['request_received_ns'] <= timing['response_ready_ns'] <= arrival:
                raise ContractError('inconsistent worker clock observations')
            if sum(timing[k] for k in ('decode_request_ns', 'backend_execute_ns', 'encode_result_ns')) != timing['response_ready_ns'] - timing['request_received_ns']:
                raise ContractError('inconsistent worker stage durations')
        except (ContractError, TypeError, KeyError) as exc:
            raise IPCFailure('BAD_RESPONSE', str(exc), process) from exc
        deserialized = time.monotonic_ns()
        value = result.format.decode(result.digits)
        decoded = time.monotonic_ns()
        # Independent oracle uses original integer inputs, only after transport succeeds.
        expected = sum(a * b for a, b in zip(lhs, rhs))
        if value != expected:
            raise IPCFailure('RESULT_MISMATCH', 'worker result differs from integer oracle', process)
        verified = time.monotonic_ns()
        if verified >= deadline or time.time_ns() >= envelope['expires_unix_ns']:
            raise IPCFailure('EXPIRED_RESPONSE', 'response verification exceeded request lifetime', process)
        host_stages = {'validate_ns': validated - start, 'encode_digits_ns': encoded - validated,
                       'serialize_request_ns': serialized - encoded,
                       'process_roundtrip_ns': received - serialized,
                       'deserialize_validate_ns': deserialized - received,
                       'decode_digits_ns': decoded - deserialized, 'oracle_verify_ns': verified - decoded}
        return {'wire_version': WIRE_VERSION, 'status': 'VERIFIED', 'backend': name, 'value': value,
                'request_id': rid, 'request_sha256': envelope_hash, 'payload_sha256': request.sha256,
                'workload_sha256': digest({'lhs': lhs, 'rhs': rhs}),
                'items': len(lhs), 'input_format': asdict(fmt), 'logical_input_digits': 2 * len(lhs) * fmt.width,
                'request_bytes': len(raw), 'response_bytes': len(response_raw),
                'host_timing_ns': {**host_stages, 'total_ns': verified - start},
                'worker_timing_ns': timing,
                'transport_windows_ns': {'request': timing['request_received_ns'] - send,
                                         'response': arrival - timing['response_ready_ns']},
                'process': process, 'execution': backend.capabilities.execution,
                'hardware_isolation': 'NOT_PROVIDED', 'native_nonbinary_hardware': 'NOT_TESTED',
                'motion_inference': 'NOT_PERFORMED', 'energy': 'NOT_MEASURED'}


def run_mixed_dot(lhs, rhs, *, timeout_s=5.0):
    """Two serial partitions, binary then ternary; never return a partial sum.

    Each partition has its own timeout. This is explicit software composition,
    not concurrent execution, fault tolerance, or an inference backend.
    """
    if type(lhs) not in (list, tuple) or type(rhs) not in (list, tuple) or not 2 <= len(lhs) == len(rhs) <= MAX_ITEMS:
        raise ContractError('mixed dot requires 2..1024 operand pairs')
    lhs, rhs = tuple(lhs), tuple(rhs)
    if any(type(v) is not int or not -(2**31) <= v < 2**31 for v in lhs + rhs):
        raise ContractError('mixed operands must be signed 32-bit integers')
    split = len(lhs) // 2
    client = SubprocessDotClient()
    runs = [client.run(lhs[:split], rhs[:split], 'binary', timeout_s=timeout_s),
            client.run(lhs[split:], rhs[split:], 'ternary', timeout_s=timeout_s)]
    value = sum(run['value'] for run in runs)
    if value != sum(a * b for a, b in zip(lhs, rhs)):
        raise IPCFailure('RESULT_MISMATCH', 'combined result differs from full oracle')
    return {'status': 'VERIFIED', 'composition': 'SERIAL_BINARY_TERNARY_PARTITIONS',
            'value': value, 'runs': runs}
