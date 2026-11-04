# SPDX-License-Identifier: Apache-2.0
from dataclasses import asdict
import json
import os
from pathlib import Path
import random
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from motionbricks.radix_ipc import (
    ROOT, MAX_FRAME, MAX_RESPONSE, ContractError, IPCFailure, SubprocessDotClient,
    backend_for, canonical, digest, exchange, pack, parse_request, run_mixed_dot, unpack,
)
from motionbricks.radix_portability import EncodedRequest

FIXTURE = ROOT / 'tests/radix_ipc/fixture_worker.py'
WORKER = ROOT / 'motionbricks/radix_worker.py'


def command(mode, *args):
    return [sys.executable, '-I', '-S', str(FIXTURE), mode, *map(str, args)]


def envelope():
    backend = backend_for('binary')
    fmt = backend.capabilities.input_format
    req = EncodedRequest(1, fmt, (fmt.encode(2),), (fmt.encode(3),))
    now = time.time_ns()
    return {'wire_version': 1, 'kind': 'integer_dot', 'request_id': 'a' * 32,
            'issued_unix_ns': now, 'expires_unix_ns': now + 5_000_000_000,
            'backend': 'binary', 'payload': json.loads(canonical(asdict(req))),
            'payload_sha256': req.sha256}


class WireTests(unittest.TestCase):
    def test_roundtrip_canonical_frame(self):
        for name in ('binary', 'ternary'):
            obj = envelope()
            obj['backend'] = name
            if name == 'ternary':
                fmt = backend_for(name).capabilities.input_format
                req = EncodedRequest(1, fmt, (fmt.encode(-5),), (fmt.encode(7),))
                obj['payload'] = json.loads(canonical(asdict(req)))
                obj['payload_sha256'] = req.sha256
            parsed, backend = parse_request(unpack(pack(obj)))
            self.assertEqual(parsed.sha256, obj['payload_sha256'])
            self.assertEqual(backend.capabilities.input_format, parsed.format)

    def test_malformed_frames(self):
        invalid_json = [b'{', b'\xff', b'{"x":1,"x":2}', b'{"x":NaN}',
                        b'{"x":Infinity}', b'{ "x":1}', b'[' * 2000 + b']' * 2000]
        frames = [b'', b'\0', b'\0' * 4, struct.pack('!I', MAX_FRAME + 1),
                  pack({'x': 1})[:-1], pack({'x': 1}) + b'x', pack({'x': 1}) * 2]
        frames += [struct.pack('!I', len(raw)) + raw for raw in invalid_json]
        for raw in frames:
            with self.subTest(raw=raw[:32]), self.assertRaises(ContractError):
                unpack(raw)

    def test_request_admission_and_expiry(self):
        mutations = [lambda x: x.update(wire_version=True), lambda x: x.update(wire_version=2),
                     lambda x: x.update(kind='other'), lambda x: x.update(request_id='bad'),
                     lambda x: x.update(backend='tpu'), lambda x: x.update(payload_sha256='0' * 64),
                     lambda x: x.update(expires_unix_ns=x['issued_unix_ns'] - 1),
                     lambda x: x.update(issued_unix_ns=x['expires_unix_ns'] + 1),
                     lambda x: x.update(expires_unix_ns=x['issued_unix_ns'] + 61_000_000_000),
                     lambda x: x.update(extra=0), lambda x: x['payload'].update(rhs=[]),
                     lambda x: x['payload'].update(schema_version=True),
                     lambda x: x['payload']['lhs'][0].__setitem__(0, True),
                     lambda x: x['payload']['format'].update(width=33)]
        for mutate in mutations:
            obj = envelope()
            mutate(obj)
            with self.subTest(obj=obj), self.assertRaises(ContractError):
                parse_request(obj)
        obj = envelope()
        with self.assertRaises(ContractError):
            parse_request(obj, obj['expires_unix_ns'])

    def test_real_worker_refuses_bad_or_duplicate_requests(self):
        bad = envelope()
        bad['expires_unix_ns'] = bad['issued_unix_ns'] - 1
        for raw in (pack(bad), pack(envelope()) * 2):
            process = subprocess.run([sys.executable, '-I', '-S', str(WORKER)],
                                     input=raw, capture_output=True, timeout=3)
            self.assertEqual(process.returncode, 2)
            self.assertEqual(unpack(process.stdout)['status'], 'FAILED')
            self.assertNotIn(b'Traceback', process.stderr)


@unittest.skipUnless(sys.platform in ('linux', 'darwin'), 'POSIX target only')
class ProcessTests(unittest.TestCase):
    def assert_reaped(self, details):
        self.assertTrue(details['reaped'])
        with self.assertRaises(ChildProcessError):
            os.waitpid(details['pid'], os.WNOHANG)

    def test_default_both_and_mixed(self):
        client = SubprocessDotClient()
        a, b = [13, -7, 0, 42], [3, 11, -9, -2]
        runs = [client.run(a, b, name) for name in ('binary', 'ternary')]
        self.assertEqual([r['value'] for r in runs], [-122, -122])
        self.assertEqual(runs[0]['workload_sha256'], runs[1]['workload_sha256'])
        self.assertNotEqual(runs[0]['payload_sha256'], runs[1]['payload_sha256'])
        self.assertEqual(run_mixed_dot(a, b)['value'], -122)
        for report in runs:
            self.assert_reaped(report['process'])
            times = report['host_timing_ns']
            self.assertEqual(times['total_ns'], sum(v for k, v in times.items() if k != 'total_ns'))
            self.assertTrue(all(v >= 0 for v in report['transport_windows_ns'].values()))
            self.assertEqual(report['native_nonbinary_hardware'], 'NOT_TESTED')

    def test_seeded_signed_vectors_and_boundaries(self):
        rng = random.Random(20261104)
        client = SubprocessDotClient()
        workloads = [([-2**31] * 1024, [-2**31] * 1024),
                     ([2**31 - 1, 2**31 - 1], [1, -1]), ([0], [0])]
        for _ in range(10):
            n = rng.randint(1, 40)
            workloads.append(([rng.randint(-2**31, 2**31 - 1) for _ in range(n)],
                              [rng.randint(-2**31, 2**31 - 1) for _ in range(n)]))
        for a, b in workloads:
            expected = sum(x*y for x, y in zip(a, b))
            for name in ('binary', 'ternary'):
                self.assertEqual(client.run(a, b, name)['value'], expected)

    def test_widths_and_input_refusal_before_spawn(self):
        client = SubprocessDotClient()
        self.assertEqual(client.run([-8], [-8], width=4)['value'], 64)
        self.assertEqual(client.run([-13], [13], 'ternary', width=3)['value'], -169)
        with patch('motionbricks.radix_ipc.exchange', side_effect=AssertionError('must not spawn')):
            for a, b in [([], []), ([1], []), ([True], [1]), ([1.0], [1]),
                         ([2**31], [1]), ([1]*1025, [1]*1025)]:
                with self.assertRaises(ContractError):
                    client.run(a, b)
            for timeout in (True, float('nan'), float('inf'), 0, 61):
                with self.assertRaises(ContractError):
                    client.run([1], [1], timeout_s=timeout)

    def test_duplicate_id_content_retry_and_bounded_ledger(self):
        client = SubprocessDotClient()
        rid = 'b' * 32
        first = client.run([2], [3], request_id=rid)
        with self.assertRaises(IPCFailure) as caught:
            client.run([2], [3], request_id=rid)
        self.assertEqual(caught.exception.code, 'DUPLICATE_ID')
        again = client.run([2], [3])
        self.assertEqual(first['value'], again['value'])
        self.assertNotEqual(first['request_id'], again['request_id'])
        with patch('motionbricks.radix_ipc.MAX_IDS', 2), self.assertRaises(IPCFailure) as caught:
            client.run([2], [3])
        self.assertEqual(caught.exception.code, 'LEDGER_FULL')

    def test_failed_attempt_id_is_spent_and_next_new_attempt_recovers(self):
        client = SubprocessDotClient(_command=command('exit'))
        with self.assertRaises(IPCFailure):
            client.run([2], [3], request_id='a'*32)
        client._command = SubprocessDotClient()._command
        with self.assertRaises(IPCFailure) as caught:
            client.run([2], [3], request_id='a'*32)
        self.assertEqual(caught.exception.code, 'DUPLICATE_ID')
        self.assertEqual(client.run([2], [3])['value'], 6)

    def test_exit_signal_and_valid_output_followed_by_failure(self):
        for mode, code in [('exit', 7), ('kill', -9), ('valid_then_exit', 8)]:
            with self.subTest(mode=mode), self.assertRaises(IPCFailure) as caught:
                SubprocessDotClient(_command=command(mode)).run([2], [3])
            self.assertEqual(caught.exception.code, 'EXIT')
            self.assertEqual(caught.exception.details['returncode'], code)
            self.assert_reaped(caught.exception.details)

    def test_timeout_hang_no_read_closed_pipes_and_kill_escalation(self):
        for mode in ('hang', 'no_read', 'closed_pipes', 'ignore_term', 'late'):
            begin = time.monotonic()
            with self.subTest(mode=mode), self.assertRaises(IPCFailure) as caught:
                SubprocessDotClient(_command=command(mode)).run([2]*1024, [3]*1024, timeout_s=0.5)
            self.assertEqual(caught.exception.code, 'TIMEOUT')
            self.assertLess(time.monotonic() - begin, 3)
            self.assert_reaped(caught.exception.details)
            if mode == 'ignore_term':
                self.assertIn('ready', caught.exception.details['stderr'])
                self.assertIn('SIGKILL', caught.exception.details['signals'])

    def test_descendant_inherits_pipes_and_is_terminated(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / 'escaped'
            with self.assertRaises(IPCFailure) as caught:
                SubprocessDotClient(_command=command('descendant', marker)).run([2], [3], timeout_s=0.5)
            self.assertEqual(caught.exception.code, 'TIMEOUT')
            self.assertIn('descendant=', caught.exception.details['stderr'])
            self.assertIn('SIGKILL', caught.exception.details['signals'])
            self.assert_reaped(caught.exception.details)
            time.sleep(1.1)
            self.assertFalse(marker.exists(), 'descendant survived cleanup')

    def test_corrupt_responses_and_no_oracle_substitution(self):
        modes = ('garbage', 'bad_utf8', 'partial', 'repeat', 'oversized', 'stale_id',
                 'stale_hash', 'version', 'payload_hash', 'bad_digit', 'wrong_format',
                 'wrong_timing', 'failed_status', 'wrong_result')
        for mode in modes:
            with self.subTest(mode=mode), self.assertRaises(IPCFailure) as caught:
                SubprocessDotClient(_command=command(mode)).run([2], [3])
            self.assertIn(caught.exception.code, ('BAD_RESPONSE', 'BAD_FRAME', 'RESULT_MISMATCH'))
            self.assertNotIn('value', caught.exception.details)
            self.assert_reaped(caught.exception.details)
            if mode == 'wrong_result':
                self.assertEqual(caught.exception.code, 'RESULT_MISMATCH')

    def test_output_flood_is_bounded(self):
        for mode in ('flood_stdout', 'flood_stderr'):
            with self.subTest(mode=mode), self.assertRaises(IPCFailure) as caught:
                SubprocessDotClient(_command=command(mode)).run([2], [3])
            self.assertIn(caught.exception.code, ('OUTPUT_LIMIT', 'BAD_FRAME'))
            self.assertLessEqual(len(caught.exception.details['stderr']), 8193)
            self.assert_reaped(caught.exception.details)

    def test_actual_old_response_replay_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'response'
            first = SubprocessDotClient(_command=command('save', path)).run([2], [3])
            self.assertEqual(first['value'], 6)
            with self.assertRaises(IPCFailure) as caught:
                SubprocessDotClient(_command=command('old_response', path)).run([2], [3])
            self.assertEqual(caught.exception.code, 'BAD_RESPONSE')

    def test_expiry_after_response_verification(self):
        client = SubprocessDotClient()
        now = time.time_ns()
        with patch('motionbricks.radix_ipc.time.time_ns', side_effect=[now, now + 60_000_000_000]):
            with self.assertRaises(IPCFailure) as caught:
                client.run([2], [3])
        self.assertEqual(caught.exception.code, 'EXPIRED_RESPONSE')

    def test_spawn_failure_and_expired_before_spawn(self):
        with self.assertRaises(IPCFailure) as caught:
            SubprocessDotClient(_command=['/nonexistent/radix-worker']).run([2], [3])
        self.assertEqual(caught.exception.code, 'SPAWN_FAILED')
        with patch('motionbricks.radix_ipc.subprocess.Popen', side_effect=AssertionError('must not spawn')):
            with self.assertRaises(IPCFailure) as caught:
                exchange(command('hang'), b'', time.monotonic_ns()-1)
        self.assertEqual(caught.exception.code, 'TIMEOUT')

    def test_parent_interrupt_still_reaps_child(self):
        created = []
        original = subprocess.Popen
        def capture(*args, **kwargs):
            process = original(*args, **kwargs)
            created.append(process)
            return process
        with patch('motionbricks.radix_ipc.subprocess.Popen', side_effect=capture):
            with patch('motionbricks.radix_ipc.selectors.DefaultSelector.select', side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    SubprocessDotClient(_command=command('hang')).run([2], [3])
        self.assertEqual(len(created), 1)
        self.assertIsNotNone(created[0].returncode)
        with self.assertRaises(ChildProcessError):
            os.waitpid(created[0].pid, os.WNOHANG)

    def test_benchmark_cli_success_and_failure(self):
        script = ROOT / 'tools/radix_ipc_benchmark.py'
        for extra, status, code in [(['--repeats', '1', '--sizes', '1'], 'VERIFIED', 0),
                                    (['--repeats', '0'], 'FAILED', 1)]:
            process = subprocess.run([sys.executable, '-S', str(script), *extra],
                                     capture_output=True, text=True, timeout=10)
            self.assertEqual(process.returncode, code, process.stderr)
            data = json.loads(process.stdout)
            self.assertEqual(data['status'], status)
            if code:
                self.assertNotIn('runs', data)

    def test_mixed_failure_never_returns_partial_sum(self):
        original = SubprocessDotClient.run
        def fail_second(client, lhs, rhs, backend, **kwargs):
            if backend == 'ternary':
                raise IPCFailure('EXIT', 'injected second partition failure')
            return original(client, lhs, rhs, backend, **kwargs)
        with patch.object(SubprocessDotClient, 'run', fail_second), self.assertRaises(IPCFailure):
            run_mixed_dot([1, 2], [3, 4])


if __name__ == '__main__':
    unittest.main()
