# SPDX-License-Identifier: Apache-2.0
"""One request on stdin, one response on stdout, then exit. Trusted worker only."""
from pathlib import Path
import sys
import time
from dataclasses import asdict

# Direct execution with -I -S: explicitly add this checkout, not caller/PYTHONPATH.
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motionbricks.radix_ipc import (
    MAX_FRAME, MAX_RESPONSE, WIRE_VERSION, digest, pack, parse_request, unpack,
)


def respond(raw, received_ns=None):
    received = time.monotonic_ns() if received_ns is None else received_ns
    envelope = unpack(raw)
    request, backend = parse_request(envelope)
    decoded = time.monotonic_ns()
    result = backend.execute(request)
    executed = time.monotonic_ns()
    data = asdict(result)
    result_hash = digest(data)
    ready = time.monotonic_ns()
    if time.time_ns() >= envelope['expires_unix_ns']:
        raise ValueError('request expired during execution')
    response = {'wire_version': WIRE_VERSION, 'request_id': envelope['request_id'],
                'request_sha256': digest(envelope), 'status': 'OK', 'result': data,
                'result_sha256': result_hash,
                'timing_ns': {'request_received_ns': received, 'response_ready_ns': ready,
                              'decode_request_ns': decoded - received,
                              'backend_execute_ns': executed - decoded,
                              'encode_result_ns': ready - executed}}
    return pack(response, MAX_RESPONSE)


def main():
    try:
        # EOF delimits this single-attempt process; parent bounds reads/writes/time.
        raw = sys.stdin.buffer.read(MAX_FRAME + 5)
        received = time.monotonic_ns()
        response = respond(raw, received)
        sys.stdout.buffer.write(response)
        sys.stdout.buffer.flush()
        return 0
    except Exception as exc:
        # Invalid requests have no trusted ID. Exit status is authoritative;
        # never serialize a traceback or substitute a computed reference value.
        error = {'wire_version': WIRE_VERSION, 'status': 'FAILED', 'error_type': type(exc).__name__}
        sys.stdout.buffer.write(pack(error, MAX_RESPONSE))
        sys.stdout.buffer.flush()
        return 2


if __name__ == '__main__':
    sys.exit(main())
