import base64
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/pyignite'))
from pyignite import FCBlock, TemperatureGuard, ThermalSafetyError
from pyignite.thermal import CheckpointStore, read_linux_cpu_temperatures


class ThermalValve(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now, self.temperature, self.alarm = 0., 70., False
        self.guard = TemperatureGuard(Path(self.tmp.name) / 'last.json', clock=lambda: self.now,
                                      reader=lambda: [{'source': 'cpu0', 'celsius': self.temperature,
                                                       'critical_alarm': self.alarm}])

    def tick(self, second, temperature):
        self.now, self.temperature = float(second), temperature
        return self.guard.poll()

    def test_sustained_over_100_latches_and_saves_last_sample(self):
        for second in range(10):
            self.tick(second, 101.)
        with self.assertRaises(ThermalSafetyError) as caught:
            self.tick(10, 103.)
        self.assertEqual(caught.exception.report['state'], 'THERMAL_TRIP')
        payload = self.guard.store.load()
        self.assertEqual(payload['state'], 'THERMAL_TRIP')
        self.assertEqual(payload['temperature_history'][-1]['sensors'][0]['celsius'], 103.)
        self.temperature = 50.
        with self.assertRaises(ThermalSafetyError):
            self.guard.poll()  # no automatic restart after cooling

    def test_exact_100_and_transient_spike_do_not_trip(self):
        for second in range(12):
            self.tick(second, 100.)
        self.assertEqual(self.guard._state, 'MONITORING')
        for second in range(12, 20):
            self.tick(second, 101.)
        self.tick(20, 99.)
        for second in range(21, 30):
            self.tick(second, 102.)
        self.assertEqual(self.guard._state, 'HOT_PENDING')

    def test_missing_invalid_and_stale_data_are_not_success(self):
        self.tick(0, 80.)
        self.guard.reader = lambda: []
        with self.assertRaises(ThermalSafetyError) as caught:
            self.guard.poll()
        self.assertEqual(caught.exception.report['state'], 'SENSOR_UNAVAILABLE')
        self.assertEqual(self.guard.store.load()['temperature_history'][-1]['sensors'][0]['celsius'], 80.)

    def test_gap_is_not_evidence_of_sustained_heat(self):
        self.tick(0, 101.)
        with self.assertRaises(ThermalSafetyError) as caught:
            self.tick(11, 102.)
        self.assertEqual(caught.exception.report['state'], 'SENSOR_STALE')

    def test_critical_alarm_stops_without_waiting(self):
        self.alarm = True
        with self.assertRaises(ThermalSafetyError) as caught:
            self.tick(0, 90.)
        self.assertEqual(caught.exception.report['state'], 'THERMAL_TRIP')

    def test_failures_to_write_are_latched_and_do_not_claim_durability(self):
        self.tick(0, 70.)
        previous = self.guard.store.path.read_bytes()
        with patch('pyignite.thermal.os.replace', side_effect=OSError('disk failure')):
            with self.assertRaises(ThermalSafetyError) as caught:
                self.tick(1, 101.)
        self.assertEqual(caught.exception.report['state'], 'CHECKPOINT_FAILED')
        self.assertEqual(caught.exception.report['durability'], 'NOT_CONFIRMED')
        self.assertEqual(self.guard.store.path.read_bytes(), previous)
        self.assertEqual(list(Path(self.tmp.name).glob('.last.json.*')), [])

    def test_result_owned_in_ram_and_restored_from_disk(self):
        self.tick(0, 70.)
        data = bytearray(b'abcd')
        self.guard.save_result(data, shape=(1,), dtype='<f4')
        data[:] = b'xxxx'
        result = self.guard.store.load()['last_completed_result']
        self.assertEqual(base64.b64decode(result['data']), b'abcd')
        record = json.loads(self.guard.store.path.read_bytes())
        record['payload']['state'] = 'tampered'
        self.guard.store.path.write_text(json.dumps(record))
        with self.assertRaises(ValueError):
            self.guard.store.load()

    def test_fc_saves_completed_result_and_rejects_post_trip_result(self):
        self.tick(0, 70.)
        layers = [(np.eye(2, dtype=np.float32), np.zeros(2, np.float32))] * 2
        for backend in ('scalar', 'fused', 'numpy'):
            model = FCBlock(layers, backend=backend, max_batch_rows=1, temperature_guard=self.guard)
            expected = np.ones((3, 2), np.float32)
            np.testing.assert_array_equal(model(expected), expected)
            result = self.guard.store.load()['last_completed_result']
            restored = np.frombuffer(base64.b64decode(result['data']), dtype=result['dtype']).reshape(result['shape'])
            np.testing.assert_array_equal(restored, expected)
        saved_result = self.guard.store.load()['last_completed_result']
        original = model._evaluate
        def hot_chunk(x):
            answer = original(x)
            self.alarm = True
            self.now = 1.
            self.guard.poll()
            return answer
        with patch.object(model, '_evaluate', side_effect=hot_chunk):
            with self.assertRaises(ThermalSafetyError):
                model(np.full((3, 2), 2, np.float32))
        self.assertEqual(self.guard.store.load()['last_completed_result'], saved_result)
        with patch.object(model, '_evaluate', wraps=original) as run:
            with self.assertRaises(ThermalSafetyError):
                model(expected)
            run.assert_not_called()

    def test_stale_guard_and_result_limit_block_before_compute(self):
        self.tick(0, 70.)
        self.guard.max_result_bytes = 4
        layers = [(np.eye(2, dtype=np.float32), np.zeros(2, np.float32))] * 2
        model = FCBlock(layers, temperature_guard=self.guard)
        with patch.object(model, '_evaluate') as run:
            with self.assertRaises(ValueError):
                model(np.ones(2, np.float32))
            run.assert_not_called()
        self.now = 5.
        with self.assertRaises(ThermalSafetyError):
            self.guard.check()

    def test_repeated_timestamps_do_not_count_as_new_samples(self):
        self.tick(0, 101.)
        for _ in range(5):
            self.tick(0, 101.)
        self.assertEqual(self.guard._hot['cpu0'][1], 1)

    def test_context_manager_stops_monitor_on_exit(self):
        with self.guard:
            self.guard.check()
        self.assertFalse(self.guard._thread.is_alive())
        with self.assertRaises(ThermalSafetyError):
            self.guard.check()

    def test_restart_cannot_silently_erase_last_result(self):
        self.tick(0, 70.)
        self.guard.save_result(b'abcd', shape=(1,), dtype='<f4')
        old = self.guard.store.load()
        with self.assertRaises(FileExistsError):
            TemperatureGuard(self.guard.store.path)
        resumed = TemperatureGuard(self.guard.store.path, reader=self.guard.reader,
                                   clock=lambda: self.now, resume_after_inspection=True)
        resumed.poll()
        restored = resumed.store.load()
        self.assertEqual(restored['last_completed_result'], old['last_completed_result'])
        self.assertEqual(restored['previous_session_last_temperature'], old['temperature_history'][-1])


class LinuxSensorSelection(unittest.TestCase):
    def test_cpu_selection_units_and_tctl_exclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for n, driver, label, value in [(0, 'nvme', 'Composite', '120000'),
                                            (1, 'coretemp', 'Core 0', '101500'),
                                            (2, 'k10temp', 'Tctl', '110000'),
                                            (3, 'k10temp', 'Tdie', '90000')]:
                d = root / f'hwmon{n}'
                d.mkdir()
                (d / 'name').write_text(driver)
                (d / 'temp1_label').write_text(label)
                (d / 'temp1_input').write_text(value)
            readings = read_linux_cpu_temperatures(root)
            self.assertEqual([s['celsius'] for s in readings], [101.5, 90.])
            (root / 'hwmon1/temp1_input').unlink()
            (root / 'hwmon3/temp1_input').unlink()
            with self.assertRaises(OSError):
                read_linux_cpu_temperatures(root)


if __name__ == '__main__':
    unittest.main()
