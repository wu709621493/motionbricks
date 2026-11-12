import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/pyignite'))
from pyignite import FCBlock, IsolatedTemperatureGuard, IsolatedIOError, ThermalSafetyError, run_supervised
from pyignite.supervisor import _Operations
from pyignite.thermal import CheckpointStore


class IsolatedValve(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'checkpoint.json'

    def guard(self, **kwargs):
        return IsolatedTemperatureGuard(self.path, reader_spec='thermal_fault_fixtures:healthy',
                                        io_timeout_seconds=1., cleanup_seconds=.15, **kwargs)

    def model(self, g, backend='scalar'):
        return FCBlock([(np.eye(2, dtype=np.float32), np.zeros(2, np.float32))] * 2,
                       temperature_guard=g, backend=backend)

    def test_complete_fc_result_roundtrip_all_backends_and_resume(self):
        g = self.guard(); g.poll()
        for backend in ('scalar', 'fused', 'numpy'):
            expected = np.ones((3, 2), np.float32)
            np.testing.assert_array_equal(self.model(g, backend)(expected), expected)
            result = g.store.load()['last_completed_result']
            data = base64.b64decode(result['data'], validate=True)
            self.assertEqual(hashlib.sha256(data).hexdigest(), result['sha256'])
            np.testing.assert_array_equal(np.frombuffer(data, dtype=result['dtype']).reshape(result['shape']), expected)
        with self.assertRaises(FileExistsError):
            self.guard()
        resumed = self.guard(resume_after_inspection=True)
        resumed.poll()
        self.assertEqual(resumed.store.load()['last_completed_result'], result)

    def test_sensor_hang_is_bounded_latched_and_does_not_trap_check_or_exit(self):
        g = self.guard(); g.poll(); self.model(g)(np.ones(2, np.float32))
        previous = g.store.load()['last_completed_result']
        g.reader_spec = 'thermal_fault_fixtures:hang'
        started = time.monotonic()
        with self.assertRaises(ThermalSafetyError) as caught:
            g.poll()
        self.assertLess(time.monotonic()-started, 3.)
        self.assertEqual(caught.exception.report['state'], 'SENSOR_UNAVAILABLE')
        receipt = caught.exception.report['last_reader_receipt']
        self.assertTrue(receipt['timed_out']); self.assertEqual(receipt['cleanup'], 'pass')
        with self.assertRaises(ThermalSafetyError):
            g.check()
        g.__exit__(None, None, None)
        self.assertEqual(g.store.load()['last_completed_result'], previous)

    def test_fsync_hang_is_bounded_and_durability_is_not_confirmed(self):
        g = self.guard(); g.poll(); self.model(g)(np.ones(2, np.float32))
        previous = self.path.read_bytes()
        g.store.store_spec = 'thermal_fault_fixtures:FsyncHangStore'
        started = time.monotonic()
        with self.assertRaises(ThermalSafetyError) as caught:
            g.poll()
        self.assertLess(time.monotonic()-started, 3.)
        self.assertEqual(caught.exception.report['state'], 'CHECKPOINT_FAILED')
        self.assertEqual(caught.exception.report['durability'], 'NOT_CONFIRMED')
        self.assertTrue(caught.exception.report['last_checkpoint_receipt']['timed_out'])
        self.assertEqual(caught.exception.report['last_checkpoint_receipt']['cleanup'], 'pass')
        with self.assertRaises(ThermalSafetyError):
            g.check()
        g.__exit__(None, None, None)
        self.assertEqual(self.path.read_bytes(), previous)

    def test_fsync_error_and_pre_replace_death_preserve_previous_complete_file(self):
        for spec in ('FsyncErrorStore', 'ReplaceInterruptedStore'):
            with self.subTest(spec=spec):
                self.path.unlink(missing_ok=True)
                g = self.guard(); g.poll(); self.model(g)(np.ones(2, np.float32))
                previous = self.path.read_bytes()
                g.store.store_spec = 'thermal_fault_fixtures:' + spec
                with self.assertRaises(ThermalSafetyError):
                    g.poll()
                self.assertEqual(g._durability, 'NOT_CONFIRMED')
                self.assertEqual(self.path.read_bytes(), previous)

    def test_constructor_filesystem_probe_is_also_isolated(self):
        started = time.monotonic()
        with self.assertRaises(IsolatedIOError) as caught:
            self.guard(checkpoint_store_spec='thermal_fault_fixtures:ExistsHangStore')
        self.assertLess(time.monotonic()-started, 3.)
        self.assertTrue(caught.exception.receipt['timed_out'])

    @unittest.skipUnless(os.name == 'posix', 'directory fsync is POSIX-specific')
    def test_failure_after_replace_is_ambiguous_not_a_durable_success(self):
        g = self.guard(); g.poll(); fn = self.model(g); fn(np.ones(2, np.float32))
        g.store.store_spec = 'thermal_fault_fixtures:DirectoryFsyncErrorStore'
        with self.assertRaises(ThermalSafetyError) as caught:
            fn(np.full(2, 2, np.float32))
        self.assertEqual(caught.exception.report['durability'], 'NOT_CONFIRMED')
        self.assertEqual(caught.exception.report['state'], 'CHECKPOINT_FAILED')
        # Atomic replace already happened: a CRC-valid complete candidate can
        # be visible despite no confirmed directory durability or returned result.
        candidate = CheckpointStore(self.path).load()['last_completed_result']
        np.testing.assert_array_equal(np.frombuffer(base64.b64decode(candidate['data']), np.float32), np.full(2,2,np.float32))
        with self.assertRaises(FileExistsError):
            self.guard()  # no silent resume/promotion after ambiguous write

    def test_invalid_sensor_corrupt_checkpoint_and_parent_callbacks_are_refused(self):
        g = self.guard(); g.reader_spec = 'thermal_fault_fixtures:invalid'
        with self.assertRaises(ThermalSafetyError):
            g.poll()
        self.path.write_text('{"schema_version":1,"payload":{},"payload_sha256":"wrong"}')
        with self.assertRaises(IsolatedIOError):
            self.guard(resume_after_inspection=True)
        with self.assertRaises(ValueError):
            self.guard(reader=lambda: [])

    def test_critical_alarm_during_compute_never_replaces_last_complete_result(self):
        g = self.guard(); g.poll(); fn = self.model(g)
        fn(np.ones(2, np.float32)); previous = g.store.load()['last_completed_result']
        def trip(h):
            g.reader_kwargs = {'critical_alarm': True}
            g.poll()  # fault occurs inside an in-progress FC invocation
            return h
        with patch.object(fn, '_evaluate', side_effect=trip):
            with self.assertRaises(ThermalSafetyError):
                fn(np.full(2, 2, np.float32))
        self.assertEqual(g.store.load()['last_completed_result'], previous)

    def test_stale_observation_remains_failure(self):
        clock = [0.]
        g = self.guard(clock=lambda: clock[0]); g.poll(); clock[0] = 3.
        with self.assertRaises(ThermalSafetyError) as caught:
            g.check()
        self.assertEqual(caught.exception.report['state'], 'SENSOR_STALE')


class Supervisor(unittest.TestCase):
    def test_unknown_durability_is_not_accepted_even_with_matching_request_identity(self):
        op = _Operations(1, .1)
        def forged(command, **kwargs):
            raw = kwargs['input_bytes']; request = json.loads(raw)
            response = {'schema_version': 1, 'nonce': request['nonce'], 'action': 'commit',
                        'request_sha256': hashlib.sha256(raw).hexdigest(), 'ok': True, 'value': 'ALL_GOOD'}
            return {'timed_out': False, 'exit_code': 0, 'cleanup': 'not_applicable',
                    'elapsed_seconds': .01, 'stdout': json.dumps(response).encode(), 'stderr': b''}
        with patch('pyignite.supervisor.run_supervised', side_effect=forged):
            with self.assertRaises(IsolatedIOError):
                op.call('commit', payload={'sequence': 1})

    def test_wall_deadline_contains_a_gil_holding_native_child(self):
        # PyDLL deliberately keeps the child interpreter's GIL while libc sleeps.
        library = 'libSystem.B.dylib' if sys.platform == 'darwin' else 'libc.so.6'
        if os.name != 'posix':
            self.skipTest('POSIX libc fixture; Windows direct-child semantics are separate')
        command = [sys.executable, '-c', 'import ctypes;ctypes.PyDLL(' + repr(library) + ').sleep(30)']
        r = run_supervised(command, timeout_seconds=.5, cleanup_seconds=.15)
        self.assertTrue(r['timed_out']); self.assertEqual(r['cleanup'], 'pass')
        self.assertIsNotNone(r['exit_code']); self.assertLess(r['elapsed_seconds'], 2.)

    def test_normal_nonzero_output_and_large_stdin_are_not_promoted(self):
        r = run_supervised([sys.executable, '-c', 'import sys;print(len(sys.stdin.buffer.read()));sys.exit(7)'],
                           timeout_seconds=3, input_bytes=b'x' * (1024 * 1024))
        self.assertFalse(r['timed_out']); self.assertEqual(r['exit_code'], 7)
        self.assertEqual(r['stdout'].strip(), b'1048576')

    def test_blocked_stdin_is_included_in_the_deadline(self):
        r = run_supervised([sys.executable, '-c', 'import time;time.sleep(30)'],
                           timeout_seconds=.3, cleanup_seconds=.15, input_bytes=b'x' * (1024 * 1024))
        self.assertTrue(r['timed_out']); self.assertEqual(r['cleanup'], 'pass')

    def test_false_success_receipts_and_late_success_are_latched(self):
        for timed_out in (False, True):
            op = _Operations(1, .1)
            fake = {'timed_out': timed_out, 'exit_code': 0, 'cleanup': 'pass',
                    'elapsed_seconds': 1., 'scope': 'mock', 'stdout': b'{"schema_version":1,"ok":true,"nonce":"wrong"}', 'stderr': b''}
            with patch('pyignite.supervisor.run_supervised', return_value=fake) as run:
                with self.assertRaises(IsolatedIOError):
                    op.call('read', reader_spec='thermal_fault_fixtures:healthy', reader_kwargs={})
                with self.assertRaises(IsolatedIOError):
                    op.call('read', reader_spec='thermal_fault_fixtures:healthy', reader_kwargs={})
                self.assertEqual(run.call_count, 1)


if __name__ == '__main__':
    unittest.main()
