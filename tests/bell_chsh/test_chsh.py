import dataclasses
import itertools
import json
import math
from pathlib import Path
import hashlib
import unittest
from unittest.mock import patch

from motionbricks import bell_chsh as b
from motionbricks.optical_quantum import (PairRequest, SimulatedClock,
                                        SimulatedPairSampler, report as zz_report,
                                        HardwareUnavailable)


class CHSHTests(unittest.TestCase):
    def setUp(self):
        self.request = b.CHSHRequest('test', 'a'*64, shots=(3000,)*4)
        self.clock = SimulatedClock()
        self.addCleanup(self.clock.close)

    def sample(self, **kwargs):
        sampler = b.SimulatedCHSHSampler(self.clock, b.Simulation(**kwargs))
        self.addCleanup(sampler.close)
        return sampler.sample(self.request)

    def test_all_deterministic_local_strategies(self):
        for a0, a1, b0, b1 in itertools.product((-1, 1), repeat=4):
            self.assertEqual(abs(a0*b0+a0*b1+a1*b0-a1*b1), 2)
        self.assertEqual(len(b.LHV_STRATEGIES), 8)
        e = [sum(t[x]*t[2+y] for t in b.LHV_STRATEGIES)/8 for x, y in b.CELLS]
        self.assertEqual(e, [.5, .5, .5, -.5])

    def test_bell_probabilities_and_tsirelson(self):
        e = []
        for x, y in b.CELLS:
            p = b.bell_probabilities(self.request.alice[x], self.request.bob[y])
            self.assertAlmostEqual(sum(p), 1)
            self.assertTrue(all(0 <= v <= 1 for v in p))
            self.assertAlmostEqual(p[0]+p[1], .5)
            e.append(p[0]-p[1]-p[2]+p[3])
        self.assertAlmostEqual(sum(s*t for s, t in zip(b.SIGNS, e)), 2*math.sqrt(2))
        self.assertEqual(b.bell_probabilities(0, 0), (.5, 0, 0, .5))

    def test_statistics_exact_and_unequal_samples(self):
        counts = [(3, 1, 0, 1, 3, 0, 0, 0, 0),
                  (4, 0, 0, 0, 0, 0, 0, 0, 0),
                  (0, 5, 0, 5, 0, 0, 0, 0, 0),
                  (0, 2, 0, 2, 0, 0, 0, 0, 0)]
        r = b.statistics(counts, .05)
        self.assertEqual(r['correlations'], [.5, 1, -1, -1])
        self.assertEqual(r['signed_S'], 1.5)
        self.assertAlmostEqual(r['standard_error'], math.sqrt(.75/7))
        rad = math.sqrt(2*(1/8+1/4+1/10+1/4)*math.log(40))
        self.assertAlmostEqual(r['confidence_interval'][0], max(-4, 1.5-rad))
        one = b.statistics([(1,)+(0,)*8]*4, .05)
        self.assertIsNone(one['standard_error'])
        # Perfect finite counts still have a nonzero Hoeffding radius.
        self.assertLess(one['confidence_interval'][0], 2)

    def test_conservation_loss_rejection(self):
        result = self.sample(loss_probability=.3, selective_rejection=.8)
        r = b.report(self.request, result)
        for audit in r['audit']:
            self.assertEqual(audit['attempted'], 3000)
            self.assertEqual(audit['accepted_coincidences']+audit['rejected_union'], 3000)
            self.assertGreater(audit['no_click'], 0)
            self.assertGreater(audit['selected_out'], 0)

    def test_all_loss_is_not_missing_data_in_primary(self):
        r = b.report(self.request, self.sample(loss_probability=1))
        self.assertEqual(r['primary_all_trials_no_click_plus_one']['signed_S'], 2)
        self.assertEqual(r['postselected_diagnostic_not_evidence']['status'], 'INSUFFICIENT_DATA')

    def test_postselection_fake_violation(self):
        result = self.sample(selective_rejection=1)
        r = b.report(self.request, result)
        self.assertEqual(r['postselected_diagnostic_not_evidence']['signed_S'], 4)
        self.assertLess(abs(r['primary_all_trials_no_click_plus_one']['signed_S']-2), .15)
        self.assertEqual(r['entanglement_verification'], 'NOT_PERFORMED')
        self.assertEqual(result.cells[0].raw, self.sample().cells[0].raw)

    def test_local_detection_loophole(self):
        result = self.sample(local_detection_attack=True)
        r = b.report(self.request, result)
        self.assertEqual(r['postselected_diagnostic_not_evidence']['signed_S'], 4)
        self.assertLess(abs(r['primary_all_trials_no_click_plus_one']['signed_S']-1.5), .15)
        self.assertTrue(all(.20 < a['accepted_coincidences']/a['attempted'] < .30
                            for a in r['audit']))

    def test_bell_and_noise(self):
        ideal = b.report(self.request, self.sample(model=b.MODELS[1]))
        noisy = b.report(self.request, self.sample(model=b.MODELS[1], flip_probability=.5))
        self.assertTrue(ideal['primary_all_trials_no_click_plus_one']['interval_excludes_local_range'])
        self.assertLess(abs(noisy['primary_all_trials_no_click_plus_one']['signed_S']), .2)
        self.assertFalse(ideal['device_measurement'])
        self.assertEqual(ideal['entanglement_verification'], 'NOT_PERFORMED')

    def test_reproducibility_hash_and_mutation(self):
        result = self.sample(seed=7)
        r = b.report(self.request, result)
        self.assertEqual(result, self.sample(seed=7))
        self.assertNotEqual(result.raw_record_sha256, self.sample(seed=8).raw_record_sha256)
        payload = json.loads(json.dumps(r))
        sha = payload.pop('record_sha256')
        self.assertEqual(sha, b.digest(payload))
        altered = dataclasses.replace(result, backend_id='changed')
        self.assertNotEqual(sha, b.report(self.request, altered)['record_sha256'])
        changed_alpha = dataclasses.replace(self.request, alpha=.01)
        with self.assertRaises(ValueError):
            b.report(changed_alpha, result)

    def test_validation(self):
        for kw in ({'shots': (0,)*4}, {'shots': (True,)*4}, {'shots': (250001,)*4},
                   {'alice': (float('nan'), 0)}, {'bob': (0,)}, {'alpha': 0},
                   {'alpha': True}, {'artifact_sha256': 'bad'}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                dataclasses.replace(self.request, **kw)
        for kw in ({'seed': True}, {'model': 'DEVICE_REPORTED'}, {'loss_probability': -1},
                   {'flip_probability': float('inf')}, {'selective_rejection': 2}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                b.Simulation(**kw)
        result = self.sample()
        for kw in ({'cells': ()}, {'backend_id': ''}, {'evidence': 'VERIFIED'},
                   {'evidence': 'DEVICE_REPORTED'}, {'raw_record_sha256': 'bad'},
                   {'cells': (b.CellCounts((0,)*9, (0,)*9),)*4}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                b.report(self.request, dataclasses.replace(result, **kw))
        for counts in (b.CellCounts((-1,)+(0,)*8, (0,)*9),
                       b.CellCounts((1,)+(0,)*8, (2,)+(0,)*8),
                       b.CellCounts((True,)+(0,)*8, (0,)*9)):
            with self.assertRaises(ValueError):
                counts.validate(1)

    def test_finite_lhv_can_exceed_two(self):
        self.request = dataclasses.replace(self.request, shots=(20,)*4)
        values = [b.report(self.request, self.sample(seed=s))[
            'primary_all_trials_no_click_plus_one'] for s in range(20)]
        self.assertTrue(any(r['signed_S'] > 2 for r in values))
        self.assertFalse(any(r['interval_excludes_local_range'] for r in values))

    def test_timeout_ownership_and_hardware(self):
        sampler = b.SimulatedCHSHSampler(self.clock)
        for timeout in (0, -1, True, float('nan')):
            with self.assertRaises(ValueError):
                sampler.sample(self.request, timeout_seconds=timeout)
        with patch.object(b.time, 'monotonic', side_effect=[0, 2]):
            with self.assertRaises(TimeoutError):
                sampler.sample(self.request, timeout_seconds=1)
        sampler.close(); sampler.close()
        self.clock.read()
        with self.assertRaises(RuntimeError):
            sampler.sample(self.request)
        with self.assertRaises(HardwareUnavailable):
            b.open_hardware()

    def test_device_label_never_means_verified(self):
        result = self.sample()
        device = dataclasses.replace(result, evidence='DEVICE_REPORTED', simulation=None,
            clock=dataclasses.replace(result.clock, evidence='DEVICE_REPORTED'))
        r = b.report(self.request, device)
        self.assertTrue(r['device_measurement'])
        self.assertEqual(r['entanglement_verification'], 'NOT_PERFORMED')

    def test_negative_s_and_no_click_assignment(self):
        plus = (4, 0, 0, 0, 0, 0, 0, 0, 0)
        minus = (0, 4, 0, 0, 0, 0, 0, 0, 0)
        r = b.statistics([minus, minus, minus, plus], .05)
        self.assertEqual(r['signed_S'], -4)
        self.assertEqual(r['abs_S'], 4)
        # (+,0),(-,0),(0,+),(0,-),(0,0) => +,-,+,-,+.
        raw = (0, 0, 1, 0, 0, 1, 1, 1, 1)
        self.assertEqual(b.statistics([raw]*4, .05)['correlations'], [.2]*4)

    def test_committed_study_integrity(self):
        root = Path(__file__).resolve().parents[2]
        study = json.loads((root/'docs/results/bell_chsh_v1.json').read_text())
        sha = study.pop('study_sha256')
        self.assertEqual(sha, b.digest(study))
        self.assertEqual(len(study['reports']), 135)
        self.assertEqual(len(study['small_sample_exploratory']), 200)
        for name, expected in study['source_sha256'].items():
            self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(), expected)
        for item in study['reports']:
            r = item['report']
            sha = r.pop('record_sha256')
            self.assertEqual(sha, b.digest(r))
            self.assertEqual(r['entanglement_verification'], 'NOT_PERFORMED')
            for audit in r['audit']:
                self.assertEqual(audit['attempted'], audit['accepted_coincidences']+audit['rejected_union'])

    def test_zz_compatibility(self):
        req = PairRequest('legacy', 'a'*64, 100)
        sampler = SimulatedPairSampler(self.clock, seed=42)
        result = sampler.sample(req)
        self.assertEqual(sum(result.counts), 100)
        self.assertEqual(result.counts[1:3], (0, 0))
        self.assertEqual(zz_report(req, result)['entanglement_verification'], 'NOT_PERFORMED')
        with self.assertRaises(ValueError):
            PairRequest('legacy', 'a'*64, basis='XX')


if __name__ == '__main__':
    unittest.main()
