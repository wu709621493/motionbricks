import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/pyignite'))
from pyignite import FCBlock

spec = importlib.util.spec_from_file_location('pyignite_doctor', ROOT / 'tools/pyignite/doctor.py')
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)


class SmallWorkingSet(unittest.TestCase):
    def test_chunks_preserve_leading_shape_and_bound_hidden_rows(self):
        rng = np.random.default_rng(1212)
        layers = [(rng.normal(0, .1, (o, i)).astype(np.float32), np.zeros(o, np.float32))
                  for i, o in [(5, 11), (11, 3), (3, 7)]]
        x = rng.normal(size=(3, 3, 10)).astype(np.float32)[..., ::2]
        for backend in ('scalar', 'fused', 'numpy'):
            model = FCBlock(layers, backend=backend, max_batch_rows=4)
            expected = FCBlock(layers, backend=backend)(x)
            with patch.object(model, '_evaluate', wraps=model._evaluate) as evaluate:
                actual = model(x)
                self.assertEqual([c.args[0].shape[0] for c in evaluate.call_args_list], [4, 4, 1])
            self.assertEqual(actual.shape, (3, 3, 7))
            if backend == 'numpy':
                np.testing.assert_allclose(actual, expected, atol=2e-5, rtol=2e-5)
            else:
                np.testing.assert_array_equal(actual, expected)
            actual[:] = 99
            np.testing.assert_allclose(model(x), expected, atol=2e-5, rtol=2e-5)

    def test_invalid_limit_and_late_overflow_fail(self):
        layers = [(np.eye(2, dtype=np.float32) * 2, np.zeros(2, np.float32))] * 2
        for limit in (True, 0, -1, 1.5):
            with self.assertRaises(ValueError):
                FCBlock(layers, max_batch_rows=limit)
        x = np.array([[1, 1], [1, 1], [np.finfo(np.float32).max, 1]], np.float32)
        for backend in ('scalar', 'fused', 'numpy'):
            with self.assertRaises(ValueError):
                FCBlock(layers, backend=backend, max_batch_rows=1)(x)

    def test_single_vector_and_one_row(self):
        layers = [(np.eye(2, dtype=np.float32), np.zeros(2, np.float32))] * 2
        for backend in ('scalar', 'fused', 'numpy'):
            model = FCBlock(layers, backend=backend, max_batch_rows=1)
            for shape in ((2,), (1, 2)):
                np.testing.assert_array_equal(model(np.ones(shape, np.float32)), np.ones(shape, np.float32))


class IsolatedProbe(unittest.TestCase):
    def run_child(self, code, timeout=5):
        return doctor.run_probe([sys.executable, '-S', '-c', code], timeout=timeout)

    def test_valid_report_and_no_health_inference(self):
        payload = dict(schema_version=1, status='PASS', checks=7, pointer_bits=32,
                       scope='native_core_smoke_only')
        result = self.run_child('print(' + repr(json.dumps(payload)) + ')')
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(doctor.event_policy([]), 'UNKNOWN')

    def test_malformed_truncated_and_false_success(self):
        for code in ('print("PASS")', 'print("{}")', 'print("x" * 9000)',
                     'import sys; print("PASS"); sys.exit(1)',
                     'import os; os.write(1, bytes([255]))'):
            self.assertNotEqual(self.run_child(code)['status'], 'PASS')

    @unittest.skipUnless(os.name == 'posix', 'POSIX signal termination')
    def test_sigill_is_contained(self):
        result = self.run_child('import os,signal,resource; resource.setrlimit(resource.RLIMIT_CORE,(0,0)); os.kill(os.getpid(),signal.SIGILL)')
        self.assertEqual(result['status'], 'CRASH')
        self.assertEqual(result['signal'], signal.SIGILL)

    def test_timeout_is_finite(self):
        start = time.monotonic()
        result = self.run_child('import time; time.sleep(60)', timeout=.2)
        self.assertEqual(result['status'], 'TIMEOUT')
        self.assertLess(time.monotonic() - start, 5)
        for value in (0, -1, math.inf, math.nan):
            with self.assertRaises(ValueError):
                self.run_child('pass', timeout=value)

    def test_missing_executable_and_event_priority(self):
        self.assertEqual(doctor.run_probe(['/no/such/pyignite-smoke'])['status'], 'START_FAILED')
        self.assertEqual(doctor.event_policy(['corrected-error']), 'REVIEW_REQUIRED')
        self.assertEqual(doctor.event_policy(['thermal-alarm', 'corrected-error']), 'STOP_AND_COOL')
        self.assertEqual(doctor.event_policy(['thermal-alarm', 'uncorrected-error']), 'QUARANTINE')
        self.assertEqual(doctor.event_policy(['data-mismatch']), 'QUARANTINE')
        with self.assertRaises(ValueError):
            doctor.event_policy(['cache-demagnetized'])

    def test_cli_blocks_on_supplied_fault_without_loading_binary(self):
        result = subprocess.run([sys.executable, '-S', str(ROOT / 'tools/pyignite/doctor.py'),
                                 '--binary', '/not/present', '--event', 'data-mismatch'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        report = json.loads(result.stdout)
        self.assertEqual(report['probe']['status'], 'NOT_RUN')
        self.assertEqual(report['action'], 'QUARANTINE')

    def test_legacy_build_cannot_overwrite_host_default(self):
        result = subprocess.run([sys.executable, str(ROOT / 'tools/pyignite/build.py'),
                                 '--profile', 'p5-x87'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()
