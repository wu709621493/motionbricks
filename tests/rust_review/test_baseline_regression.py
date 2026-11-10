import copy
import unittest

from tools.rust_review.baseline_regression import EXPECTED, KNOWN, assess


def fixture():
    return {'status': 'FAIL', 'atol': 2e-5, 'rtol': 2e-5,
            'python': '3.12', 'numpy': '2.3.5', 'torch': '2.15.0', 'platform': 'test',
            'cases': [{'name': name, 'status': 'FAIL' if name == KNOWN else 'PASS',
                       'repeat_identical': True, 'violations': 1 if name == KNOWN else 0,
                       'elements': 2, 'max_abs_error': .0001 if name == KNOWN else 0,
                       'actual_sha256': 'a', 'reference_sha256': 'b', 'violations_sha256': 'c'}
                      for name in sorted(EXPECTED)]}


class RegressionGate(unittest.TestCase):
    def test_identical_known_failure_is_not_claimed_as_parity_pass(self):
        result = assess(fixture(), fixture())
        self.assertEqual(result['status'], 'PASS_NO_NEW_REGRESSION')
        self.assertEqual(result['strict_current_parity'], 'FAIL')

    def test_new_failure_rejected(self):
        base, current = fixture(), fixture()
        case = next(c for c in current['cases'] if c['name'] != KNOWN)
        case.update(status='FAIL', violations=1)
        with self.assertRaisesRegex(AssertionError, 'new parity failure'):
            assess(base, current)

    def test_changed_known_failure_rejected(self):
        for key, value in [('actual_sha256', 'different'), ('reference_sha256', 'different'),
                           ('violations_sha256', 'different'), ('violations', 2), ('max_abs_error', .0002)]:
            current = fixture()
            next(c for c in current['cases'] if c['name'] == KNOWN)[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(AssertionError, 'known failure changed'):
                assess(fixture(), current)

    def test_missing_case_tolerance_or_unexpected_baseline_fail_rejected(self):
        current = fixture()
        current['cases'].pop()
        with self.assertRaises(AssertionError): assess(fixture(), current)
        current = fixture()
        current['atol'] = 1e-3
        with self.assertRaises(AssertionError): assess(fixture(), current)
        base = fixture()
        next(c for c in base['cases'] if c['name'] != KNOWN).update(status='FAIL', violations=1)
        with self.assertRaises(AssertionError): assess(base, fixture())

    def test_fixed_current_case_is_accepted(self):
        current = copy.deepcopy(fixture())
        current['status'] = 'PASS'
        next(c for c in current['cases'] if c['name'] == KNOWN).update(status='PASS', violations=0, max_abs_error=0)
        self.assertEqual(assess(fixture(), current)['known_parity_failures'], [])


if __name__ == '__main__':
    unittest.main()
