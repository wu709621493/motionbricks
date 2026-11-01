import dataclasses
import json
import subprocess
import sys
import threading
from types import SimpleNamespace
import unittest

from motionbricks.cold_atoms import (
    BECRequest, BECResult, PopulationShot, SimulatedBEC500, link_experiments,
    open_hardware, report,
)
from motionbricks.optical_quantum import (
    HardwareUnavailable, PairRequest, SimulatedClock, SimulatedPairSampler,
    report as optical_report,
)


class BECCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.clock = SimulatedClock()
        self.backend = SimulatedBEC500(self.clock, seed=7)
        self.optical = SimulatedPairSampler(self.clock, seed=7)
        for obj in (self.clock, self.backend, self.optical):
            self.addCleanup(obj.close)
        self.request = BECRequest('bec-1', 'a' * 64, shots=3)
        self.pair = PairRequest('photon-1', 'a' * 64, shots=5)

    def test_500_atom_accounting_and_repeat_independence(self):
        first = self.backend.sample(self.request)
        self.backend.sample(dataclasses.replace(self.request, request_id='other'))
        self.assertEqual(first, self.backend.sample(self.request))
        self.assertEqual(len(first.populations), 3)
        for shot in first.populations:
            self.assertEqual(shot.loaded_atoms, 500)
            self.assertEqual(shot.mode_0 + shot.mode_1 + shot.lost_atoms, 500)
        r = report(self.request, first)
        self.assertEqual(r['result']['evidence'], 'SIMULATED')
        self.assertEqual(r['condensation_verification'], 'NOT_PERFORMED')
        self.assertEqual(r['entanglement_verification'], 'NOT_PERFORMED')

    def test_requests_reject_unsupported_scale_and_operations(self):
        for key, value in [('atom_count', 499), ('atom_count', 501), ('atom_count', 500.0),
                           ('shots', True), ('shots', 0), ('shots', 4097),
                           ('species', 'Cs-133'), ('operation', 'universal_circuit'),
                           ('preparation_id', ''), ('request_id', ''), ('artifact_sha256', 'bad')]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                dataclasses.replace(self.request, **{key: value})

    def test_population_loss_and_bad_accounting(self):
        PopulationShot(490, 200, 280, 10)
        PopulationShot(0, 0, 0, 0)
        for values in ((501, 250, 251, 0), (500, 250, 250, 1),
                       (500, -1, 501, 0), (True, 1, 0, 0), (500, 1.0, 499, 0)):
            with self.assertRaises(ValueError):
                PopulationShot(*values)
        result = self.backend.sample(self.request)
        loss = dataclasses.replace(result, populations=(PopulationShot(490, 200, 280, 10),), rejected_shots=2)
        loss.validate(self.request)
        dataclasses.replace(result, populations=(), rejected_shots=3).validate(self.request)

    def test_result_identity_evidence_and_shots(self):
        result = self.backend.sample(self.request)
        for key, value in [('request_id', 'stale'), ('artifact_sha256', 'b' * 64),
                           ('species', 'other'), ('operation', 'other'), ('preparation_id', 'other'),
                           ('populations', []), ('rejected_shots', 1), ('rejected_shots', True),
                           ('backend_id', ''), ('evidence', 'VERIFIED'),
                           ('evidence', 'DEVICE_REPORTED'), ('raw_record_sha256', 'bad'),
                           ('clock', None)]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                report(self.request, dataclasses.replace(result, **{key: value}))
        device_clock = dataclasses.replace(self.clock.read(), evidence='DEVICE_REPORTED')
        device = dataclasses.replace(result, evidence='DEVICE_REPORTED', clock=device_clock)
        with self.assertRaises(ValueError):
            device.validate(self.request)
        # Declared device evidence is schema-valid, never proof of real hardware.
        declared = dataclasses.replace(device, raw_record_sha256='c' * 64)
        self.assertEqual(report(self.request, declared)['condensation_verification'], 'NOT_PERFORMED')

    def test_legacy_optical_schema_preserved_and_linked(self):
        pair_result = self.optical.sample(self.pair)
        before = optical_report(self.pair, pair_result)
        bundle = link_experiments(self.pair, pair_result, self.request, self.backend.sample(self.request))
        self.assertEqual(bundle['optical'], before)
        self.assertEqual(bundle['optical']['schema_version'], 1)
        self.assertIsNone(bundle['cpu_reference'])
        self.assertEqual(bundle['synchronization'], 'NOT_VERIFIED')
        self.assertEqual(bundle['hybrid_entanglement'], 'NOT_VERIFIED')
        self.assertEqual(bundle['cold_atoms']['result']['clock'], before['result']['clock'])
        json.dumps(bundle, allow_nan=False)

    def test_mismatched_artifacts_and_response_rejected(self):
        other = dataclasses.replace(self.request, artifact_sha256='b' * 64)
        with self.assertRaises(ValueError):
            link_experiments(self.pair, self.optical.sample(self.pair), other, self.backend.sample(other))
        with self.assertRaises(ValueError):
            link_experiments(self.pair, self.optical.sample(self.pair), self.request,
                             dataclasses.replace(self.backend.sample(self.request), request_id='stale'))

    def cpu_fixture_report(self):
        # Exercise the actual CPUReference.run report producer with an explicitly
        # fake session. This is schema compatibility evidence, NOT G1 inference.
        import numpy as np
        from motionbricks.cpu_reference import CPUReference, G1Contract, synthetic_request
        ref = CPUReference.__new__(CPUReference)
        ref._lock = threading.Lock()
        ref.contract = G1Contract()
        values = {n: np.zeros(s['shape'], dtype=s['dtype']) for n, s in ref.contract.outputs.items()}
        values['pred_num_tokens'][0] = 6
        ref._session = SimpleNamespace(run=lambda names, inputs: [values[n] for n in names])
        ref.metadata = {'model_sha256': 'a' * 64, 'manifest_sha256': 'b' * 64,
                        'device': 'CPU', 'providers': ['CPUExecutionProvider'],
                        'rig': 'unitree_g1', 'batch_size': 1,
                        'test_fixture': 'FAKE SESSION; NO REAL INFERENCE'}
        with ref:
            return ref.run(synthetic_request())[1]

    def test_cpu_report_producer_compatibility_and_copy(self):
        cpu = self.cpu_fixture_report()
        bundle = link_experiments(self.pair, self.optical.sample(self.pair), self.request,
                                  self.backend.sample(self.request), cpu_report=cpu)
        self.assertEqual(bundle['cpu_reference'], cpu)
        self.assertEqual(bundle['cross_backend_parity'], 'NOT_TESTED')
        cpu['providers'].append('fake')
        self.assertEqual(bundle['cpu_reference']['providers'], ['CPUExecutionProvider'])

    def test_cpu_report_rejects_contract_only_or_wrong_identity(self):
        cpu = self.cpu_fixture_report()
        for key, value in [('evidence', 'CONTRACT_ONLY'), ('model_sha256', 'b' * 64),
                           ('providers', ['CUDAExecutionProvider']), ('input_sha256', None),
                           ('rig', 'soma'), ('batch_size', True), ('device', 'TPU'),
                           ('inference_seconds', float('nan'))]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                link_experiments(self.pair, self.optical.sample(self.pair), self.request,
                                 self.backend.sample(self.request), cpu_report=dict(cpu, **{key: value}))

    def test_hash_changes_when_acquisition_changes(self):
        result = self.backend.sample(self.request)
        a = report(self.request, result)
        b = report(self.request, dataclasses.replace(result, backend_id='different'))
        self.assertNotEqual(a['record_sha256'], b['record_sha256'])
        self.assertEqual(a, report(self.request, result))

    def test_lifecycle_timeout_and_no_fallback(self):
        with self.assertRaises(HardwareUnavailable):
            open_hardware()
        for timeout in (0, -1, True, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                self.backend.sample(self.request, timeout_seconds=timeout)
        self.backend.close()
        self.backend.close()
        with self.assertRaises(RuntimeError):
            self.backend.sample(self.request)
        self.optical.sample(self.pair)  # borrowed clock still works
        self.clock.close()
        with self.assertRaises(RuntimeError):
            SimulatedBEC500(self.clock).sample(self.request)

    def test_cli_and_gpu_free_import(self):
        for mode, code in [('simulate', 0), ('hardware', 2)]:
            p = subprocess.run([sys.executable, '-m', 'motionbricks.cold_atoms', '--mode', mode,
                                '--artifact-sha256', 'a' * 64, '--link-optical'],
                               text=True, capture_output=True)
            self.assertEqual(p.returncode, code, p.stderr)
            record = json.loads(p.stdout)
            if mode == 'simulate':
                self.assertEqual(record['cold_atoms']['result']['evidence'], 'SIMULATED')
                self.assertEqual(record['optical']['result']['evidence'], 'SIMULATED')
            else:
                self.assertEqual(record['status'], 'BLOCKED')
        subprocess.run([sys.executable, '-S', '-c',
                        'import motionbricks.cold_atoms; import sys; '
                        'assert not any(m in sys.modules for m in '
                        '["numpy", "onnxruntime", "warp", "tensorrt", "jax"])'], check=True)


if __name__ == '__main__':
    unittest.main()
