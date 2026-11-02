"""Run CPU evidence checks and emit honest L1-L7 evidence coverage as JSON."""
import json
import hashlib
from pathlib import Path
import platform
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests/zero_guard'))
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=2).run(suite)
    passed = result.wasSuccessful()
    report = {
        'schema_version': 1,
        'framework': 'Perception Theory: task-specific evidence mapping, not a validated scale',
        'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                          for name in ('motionbricks/zero_guard.py',
                                       'motionbricks/optical_quantum.py',
                                       'motionbricks/sleep_mode.py',
                                       'tests/zero_guard/test_zero_guard.py',
                                       'tools/zero_guard/evaluate.py')},
        'python': platform.python_version(), 'platform': platform.platform(),
        'tests_run': result.testsRun, 'failures': len(result.failures),
        'errors': len(result.errors), 'cpu_checks_passed': passed,
        'layers': [
            {'layer': 'L1', 'status': 'SOFTWARE_EVIDENCE_ONLY',
             'evidence': 'Zero data distinguished from zero-denominator/domain errors.'},
            {'layer': 'L2', 'status': 'SOFTWARE_EVIDENCE_ONLY',
             'evidence': 'Structured operation/status/reason; prose paraphrase still needs review.'},
            {'layer': 'L3', 'status': 'SOFTWARE_EVIDENCE_ONLY',
             'evidence': 'Optical statistics and sleep supervisor transfer tests executed.'},
            {'layer': 'L4', 'status': 'NOT_TESTED',
             'evidence': 'No three-person comprehension study performed.'},
            {'layer': 'L5', 'status': 'NOT_TESTED',
             'evidence': 'Human/robot perception-gap measurement absent; translation variant documented.'},
            {'layer': 'L6', 'status': 'NOT_TESTED',
             'evidence': 'No physical force or temperature experiment performed.'},
            {'layer': 'L7', 'status': 'DEFINITION_REQUIRED',
             'evidence': 'Latest user-authorized definition not found; no definition invented.'},
        ],
        'all_layers_validated': False,
    }
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
