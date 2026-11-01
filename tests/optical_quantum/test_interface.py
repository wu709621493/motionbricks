import dataclasses
import json
import subprocess
import sys
import unittest

from motionbricks.optical_quantum import (
    ClockReading, HardwareUnavailable, PairRequest, SimulatedClock,
    SimulatedPairSampler, open_hardware, report,
)


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.clock = SimulatedClock()
        self.sampler = SimulatedPairSampler(self.clock, seed=42)
        self.addCleanup(self.clock.close)
        self.addCleanup(self.sampler.close)
        self.request = PairRequest('test', 'a' * 64)

    def test_reproducible_independent_requests(self):
        first = self.sampler.sample(self.request)
        self.sampler.sample(PairRequest('other', 'b' * 64, 20))
        self.assertEqual(first, self.sampler.sample(self.request))
        self.assertEqual(sum(first.counts), self.request.shots)
        self.assertEqual(first.evidence, 'SIMULATED')
        self.assertEqual(first.clock.evidence, 'SIMULATED')

    def test_report_boundaries_and_hash(self):
        result = self.sampler.sample(self.request)
        r = report(self.request, result)
        self.assertEqual(r['entanglement_verification'], 'NOT_PERFORMED')
        self.assertEqual(r['motion_inference'], 'NOT_PERFORMED')
        self.assertEqual(r['record_sha256'], report(self.request, result)['record_sha256'])
        changed = dataclasses.replace(result, backend_id='different')
        self.assertNotEqual(r['record_sha256'], report(self.request, changed)['record_sha256'])
        json.dumps(r, allow_nan=False)

    def test_invalid_requests(self):
        for field, value in [('shots', 0), ('shots', True), ('shots', 1000001),
                             ('artifact_sha256', 'bad'), ('basis', 'XX'), ('request_id', '')]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                dataclasses.replace(self.request, **{field: value})

    def test_invalid_clock(self):
        reading = self.clock.read()
        for field, value in [('ticks', -1), ('ticks', True), ('tick_period_seconds', '0'),
                             ('tick_period_seconds', 'NaN'), ('uncertainty_seconds', '-1'),
                             ('uncertainty_seconds', 'Infinity'), ('uncertainty_seconds', 0.1),
                             ('calibration_id', ''), ('evidence', 'VERIFIED')]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                dataclasses.replace(reading, **{field: value})
        fine = dataclasses.replace(reading, ticks=10**30, tick_period_seconds='1e-18')
        self.assertEqual(fine.ticks, 10**30)

    def test_invalid_results(self):
        result = self.sampler.sample(self.request)
        for field, value in [('request_id', 'stale'), ('artifact_sha256', 'b' * 64),
                             ('basis', 'XX'), ('counts', (-1, 0, 0, 101)),
                             ('counts', (True, 0, 0, 99)), ('counts', (1, 2)),
                             ('rejected_shots', 1), ('evidence', 'DEVICE_REPORTED'),
                             ('raw_record_sha256', 'bad'), ('backend_id', '')]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                report(self.request, dataclasses.replace(result, **{field: value}))
        rejected = dataclasses.replace(result, counts=(0, 0, 0, 0), rejected_shots=100)
        rejected.validate(self.request)

    def test_close_and_clock_ownership(self):
        self.sampler.close()
        self.sampler.close()
        self.clock.read()  # borrowed clock remains open
        with self.assertRaises(RuntimeError):
            self.sampler.sample(self.request)
        self.clock.close()
        self.clock.close()
        with self.assertRaises(RuntimeError):
            self.clock.read()

    def test_unavailable_never_falls_back(self):
        with self.assertRaises(HardwareUnavailable):
            open_hardware()
        for timeout in (0, -1, float('nan'), float('inf'), True):
            with self.assertRaises(ValueError):
                self.sampler.sample(self.request, timeout_seconds=timeout)

    def test_cli(self):
        for mode, code in [('simulate', 0), ('hardware', 2)]:
            p = subprocess.run([sys.executable, '-m', 'motionbricks.optical_quantum',
                                '--mode', mode, '--artifact-sha256', 'a' * 64],
                               text=True, capture_output=True)
            self.assertEqual(p.returncode, code, p.stderr)
            result = json.loads(p.stdout)
            if mode == 'simulate':
                self.assertEqual(result['result']['evidence'], 'SIMULATED')
            else:
                self.assertEqual(result['status'], 'BLOCKED')


if __name__ == '__main__':
    unittest.main()
