import json
import math
import unittest
from dataclasses import asdict, replace
from motionbricks.zero_guard import divide, log, normalize, ZeroDomainError
from motionbricks.optical_quantum import (
    PairRequest, SimulatedClock, SimulatedPairSampler, sampling_statistics,
)
from motionbricks.sleep_mode import BalanceSample, Mode, SleepSupervisor


class ZeroGuardTests(unittest.TestCase):
    def test_ordinary_results(self):
        self.assertEqual(divide(6, -3).value, -2)
        self.assertEqual(divide(0, 3).value, 0)
        self.assertEqual(log(1).value, 0)
        self.assertEqual(normalize([3, 0, 4]).value, (0.6, 0, 0.8))

    def test_signed_zero_and_indeterminate(self):
        for a in (0, 1, -1):
            for b in (0.0, -0.0):
                with self.subTest(a=a, b=b):
                    with self.assertRaises(ZeroDomainError): divide(a, b)
                    r = divide(a, b, policy='undefined')
                    self.assertIsNone(r.value)
                    self.assertEqual(r.status, 'UNDEFINED')

    def test_fallback_is_not_a_valid_answer(self):
        r = divide(1, 0, policy='fallback', fallback=0)
        self.assertEqual((r.value, r.status, r.reason), (0, 'FALLBACK', 'zero_denominator'))
        self.assertEqual(log(0, policy='fallback', fallback=-2).status, 'FALLBACK')
        self.assertEqual(normalize([0, 0], policy='fallback', fallback=[0, 0]).status, 'FALLBACK')

    def test_zero_log_and_norm(self):
        for call in (lambda: log(0), lambda: normalize([0, -0.0])):
            with self.assertRaises(ZeroDomainError): call()
        self.assertIsNone(log(0, policy='undefined').value)
        self.assertIsNone(normalize([0], policy='undefined').value)

    def test_invalid_inputs_are_not_hidden(self):
        for v in (float('nan'), float('inf'), -float('inf'), 10**400):
            for call in (lambda: divide(v, 0, policy='undefined'),
                         lambda: log(v, policy='undefined'),
                         lambda: normalize([v, 0], policy='undefined')):
                with self.assertRaises(ValueError): call()
        for v in (True, '0', None, 0j):
            with self.assertRaises(TypeError): divide(v, 0, policy='undefined')
        with self.assertRaises(ValueError): log(-1, policy='fallback', fallback=1)
        with self.assertRaises(ValueError): normalize([], policy='undefined')

    def test_policy_validation_even_on_good_inputs(self):
        for call in (lambda: divide(1, 2, policy='typo'),
                     lambda: log(1, policy='fallback'),
                     lambda: divide(1, 2, fallback=0),
                     lambda: normalize([1, 2], policy='fallback', fallback=[1]),
                     lambda: divide(1, 0, policy='fallback', fallback=float('nan'))):
            with self.assertRaises(ValueError): call()

    def test_near_zero_and_extreme_vectors(self):
        self.assertEqual(divide(1e-300, 1e-300).value, 1)
        self.assertEqual(divide(5e-324, 5e-324).value, 1)
        self.assertTrue(math.isfinite(log(5e-324).value))
        with self.assertRaises(OverflowError): divide(1e308, 1e-308, policy='undefined')
        for v in ([1e308, 1e308], [5e-324, 5e-324]):
            unit = normalize(v).value
            self.assertAlmostEqual(sum(x*x for x in unit), 1)

    def test_json_has_no_nan(self):
        r = divide(0, 0, policy='undefined')
        self.assertIsNone(json.loads(json.dumps(asdict(r), allow_nan=False))['value'])

    def test_optical_all_rejected_vs_true_zero_correlation(self):
        req = PairRequest('zero-study', 'a'*64, shots=4)
        result = SimulatedPairSampler(SimulatedClock()).sample(req)
        missing = sampling_statistics(req, replace(result, counts=(0, 0, 0, 0), rejected_shots=4))
        self.assertEqual(missing['zz_correlation']['status'], 'UNDEFINED')
        self.assertIsNone(missing['zz_correlation']['value'])
        balanced = sampling_statistics(req, replace(result, counts=(1, 1, 1, 1)))
        self.assertEqual(balanced['zz_correlation']['value'], 0)
        self.assertEqual(balanced['zz_correlation']['status'], 'OK')
        with self.assertRaises(ValueError):
            sampling_statistics(req, replace(result, counts=(0, 0, 0, 0)))

    def test_sleep_zero_is_data_and_duplicate_time_is_fault(self):
        supervisor = SleepSupervisor()
        sample = BalanceSample(0, 0, 0, 0.1, True, True)
        self.assertEqual(supervisor.tick(sample, 0, sleep_requested=True).mode, Mode.SETTLING)
        self.assertEqual(supervisor.tick(sample, 0, sleep_requested=True).mode, Mode.FAULT)


if __name__ == '__main__':
    unittest.main()
