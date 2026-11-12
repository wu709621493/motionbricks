import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('pe_diagnosis', ROOT/'tools/pyignite/diagnose_pe.py')
diagnosis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnosis)


class StrictStatus(unittest.TestCase):
    def test_original_tolerance_failure_and_nonfinite_are_preserved(self):
        original = np.zeros(2, np.float32)
        result, mask = diagnosis.comparison(np.array([0, 0.00012207], np.float32), original)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(mask.tolist(), [False, True])
        result, _ = diagnosis.comparison(original, original)
        self.assertEqual(result['status'], 'PASS')
        result, _ = diagnosis.comparison(np.array([np.nan, 0], np.float32), original)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual((diagnosis.ATOL, diagnosis.RTOL), (2e-5, 2e-5))


if __name__ == '__main__':
    unittest.main()
