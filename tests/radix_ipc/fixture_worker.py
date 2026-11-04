# SPDX-License-Identifier: Apache-2.0
"""Deliberately broken, test-only subprocesses. Never selected by production CLI."""
import os
from pathlib import Path
import signal
import struct
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from motionbricks.radix_ipc import MAX_FRAME, MAX_RESPONSE, digest, pack, unpack
from motionbricks.radix_worker import respond

mode = sys.argv[1]
if mode == 'no_read':
    time.sleep(30)
    sys.exit(0)
raw = sys.stdin.buffer.read(MAX_FRAME + 5)
if mode == 'exit':
    sys.exit(7)
if mode == 'kill':
    os.kill(os.getpid(), signal.SIGKILL)
if mode == 'hang':
    time.sleep(30)
if mode == 'ignore_term':
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    sys.stderr.write('ready\n')
    sys.stderr.flush()
    time.sleep(30)
if mode == 'descendant':
    pid = os.fork()
    if pid == 0:
        # Report parent timeout cleanup by trying to create a late marker.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        time.sleep(1.0)
        Path(sys.argv[2]).write_text('escaped')
        os._exit(0)
    sys.stderr.write('descendant=' + str(pid) + '\n')
    sys.stderr.flush()
    sys.exit(0)  # child keeps inherited output pipes open
if mode == 'closed_pipes':
    os.close(1)
    os.close(2)
    time.sleep(30)
if mode == 'flood_stderr':
    while True:
        os.write(2, b'x' * 4096)
if mode == 'flood_stdout':
    os.write(1, struct.pack('!I', MAX_RESPONSE))
    while True:
        os.write(1, b'x' * 4096)
if mode == 'oversized':
    os.write(1, struct.pack('!I', MAX_RESPONSE + 1))
    sys.exit(0)
if mode == 'garbage':
    os.write(1, b'\x00\x00\x00\x01{')
    sys.exit(0)
if mode == 'bad_utf8':
    os.write(1, b'\x00\x00\x00\x01\xff')
    sys.exit(0)
response = respond(raw)
if mode == 'partial':
    response = response[:-5]
elif mode == 'repeat':
    response += response
elif mode == 'old_response':
    response = Path(sys.argv[2]).read_bytes()
elif mode == 'save':
    Path(sys.argv[2]).write_bytes(response)
else:
    data = unpack(response, MAX_RESPONSE)
    if mode == 'stale_id':
        data['request_id'] = 'f' * 32
    elif mode == 'stale_hash':
        data['request_sha256'] = '0' * 64
    elif mode == 'version':
        data['wire_version'] = True
    elif mode == 'payload_hash':
        data['result_sha256'] = '0' * 64
    elif mode == 'bad_digit':
        data['result']['digits'][0] = 2
        data['result_sha256'] = digest(data['result'])
    elif mode == 'wrong_result':
        data['result']['digits'][0] ^= 1
        data['result_sha256'] = digest(data['result'])
    elif mode == 'wrong_format':
        data['result']['format']['width'] += 1
        data['result_sha256'] = digest(data['result'])
    elif mode == 'wrong_timing':
        data['timing_ns']['backend_execute_ns'] = -1
    elif mode == 'failed_status':
        data['status'] = 'FAILED'
    response = pack(data, MAX_RESPONSE)
if mode == 'late':
    time.sleep(1)
sys.stdout.buffer.write(response)
sys.stdout.buffer.flush()
if mode == 'valid_then_exit':
    sys.exit(8)
