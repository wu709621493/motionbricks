import dataclasses
import json
import math
import subprocess
import sys
import unittest
from unittest.mock import patch

import numpy as np
from scipy.linalg import eigh_tridiagonal

from motionbricks.bec_dynamics import (
    DIMENSION, N, DynamicsBEC500, Parameters, compare_initial_states,
    evolve, hamiltonian, initial_vector,
)
from motionbricks.cold_atoms import BECRequest, link_experiments
from motionbricks.optical_quantum import PairRequest, SimulatedClock, SimulatedPairSampler


class DynamicsTests(unittest.TestCase):
    def test_hermitian_and_known_matrix_elements(self):
        p = Parameters(tunnelling=0.3, interaction=0.01, bias=0.2)
        h = hamiltonian(p).toarray()
        self.assertEqual(h.shape, (501, 501))
        np.testing.assert_array_equal(h, h.T.conj())
        self.assertAlmostEqual(h[0, 0], .01 * 250**2 - .2 * 250)
        self.assertAlmostEqual(h[0, 1], -.3 * np.sqrt(500))
        self.assertEqual(h[0, 2], 0)

    def test_initial_states_and_extremes(self):
        for z, index in ((-1, 0), (1, 500)):
            state = initial_vector(Parameters(imbalance=z))
            self.assertEqual(abs(state[index]), 1)
            self.assertEqual(np.count_nonzero(state), 1)
        p = Parameters(imbalance=.2, phase=.3)
        state = initial_vector(p)
        probs = abs(state)**2
        n = np.arange(501)
        self.assertAlmostEqual(probs @ n, 300, places=9)
        self.assertAlmostEqual(probs @ (n - 300)**2, 120, places=8)
        self.assertAlmostEqual(float(np.linalg.norm(state)), 1)

    def test_noninteracting_rabi_analytic(self):
        # N particles initially in mode 0 undergo independent Rabi oscillations.
        p = Parameters(interaction=0, initial_state='fock', fock_n0=500,
                       duration=math.pi / 2, samples=17)
        result = evolve(p)
        expected = np.cos(2 * result.times)
        np.testing.assert_allclose(result.report['imbalance'], expected, atol=2e-9)
        expected_variance = N * np.sin(2 * result.times)**2
        np.testing.assert_allclose(result.report['number_difference_variance'], expected_variance, atol=2e-7)
        self.assertGreater(abs(result.states[-1, 0])**2, 1 - 1e-8)

    def test_diagonal_interacting_solution(self):
        p = Parameters(tunnelling=0, interaction=.004, bias=.1, duration=.4, samples=5)
        result = evolve(p)
        expected = np.exp(-1j * np.outer(result.times, hamiltonian(p).diagonal())) * initial_vector(p)
        np.testing.assert_allclose(result.states, expected, atol=1e-9)
        np.testing.assert_allclose(abs(result.states)**2,
                                   np.broadcast_to(abs(initial_vector(p))**2, result.states.shape), atol=1e-9)

    def test_independent_spectral_solver(self):
        p = Parameters(duration=.2, samples=3)
        h = hamiltonian(p)
        eigenvalues, eigenvectors = eigh_tridiagonal(h.diagonal(), h.diagonal(1))
        expected = eigenvectors @ (np.exp(-1j * eigenvalues * p.duration)
                                  * (eigenvectors.T @ initial_vector(p)))
        np.testing.assert_allclose(evolve(p).states[-1], expected, atol=2e-9)

    def test_conservation_repeat_and_observable_bounds(self):
        p = Parameters(duration=.3, samples=5)
        a, b = evolve(p), evolve(p)
        np.testing.assert_array_equal(a.states, b.states)
        self.assertEqual(a.report['trajectory_sha256'], b.report['trajectory_sha256'])
        self.assertLess(a.report['max_norm_error'], 1e-8)
        self.assertLess(a.report['max_energy_error_over_hbar'] / a.report['energy_error_scale'], 1e-8)
        self.assertTrue(np.all(np.abs(a.report['imbalance']) <= 1 + 1e-8))
        self.assertTrue(np.all(np.array(a.report['first_order_coherence']) <= 1 + 1e-8))
        self.assertTrue(np.all(np.array(a.report['number_difference_variance']) >= 0))
        self.assertEqual(a.report['evidence'], 'NUMERICAL_SIMULATION')
        json.dumps(a.report, allow_nan=False)

    def test_solver_failure_not_hidden_by_renormalization(self):
        for value in (2, np.nan):
            bad = np.full((3, 501), value, dtype=complex)
            with patch('motionbricks.bec_dynamics.expm_multiply', return_value=bad):
                with self.assertRaises(RuntimeError):
                    evolve(Parameters(samples=3))

    def test_parameters_and_work_budget(self):
        for field, value in [('duration', 0), ('samples', True), ('samples', 1002),
                             ('tunnelling', float('inf')), ('bias', float('nan')),
                             ('interaction', True), ('interaction', 1e10), ('imbalance', 2),
                             ('phase', 1e308), ('fock_n0', -1), ('fock_n0', 500.0),
                             ('initial_state', 'unknown')]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                Parameters(**{field: value})

    def test_readout_distinguishability_and_unitary_bound(self):
        comparison = compare_initial_states(Parameters(duration=.2, samples=5))
        for case in comparison['cases'].values():
            tv = np.array(case['number_readout_total_variation'])
            distance = np.array(case['pure_state_trace_distance'])
            self.assertAlmostEqual(tv[0], 0, places=9)
            np.testing.assert_allclose(distance, distance[0], atol=1e-8)
            self.assertTrue(np.all(tv <= distance + 1e-8))
            self.assertTrue(np.all(np.array(case['equal_prior_single_shot_success']) >= .5))
        self.assertEqual(comparison['quantum_advantage'], 'NOT_TESTED')
        near_identical = compare_initial_states(Parameters(phase=math.pi, duration=.1, samples=3))
        for case in near_identical['cases'].values():
            self.assertLess(max(case['number_readout_total_variation']), 1e-8)
        with self.assertRaises(ValueError):
            compare_initial_states(Parameters(initial_state='fock'))

    def test_adapter_optical_link_and_lifecycle(self):
        clock = SimulatedClock()
        backend = DynamicsBEC500(clock, Parameters(duration=.1, samples=3), seed=7)
        optical = SimulatedPairSampler(clock)
        try:
            request = BECRequest('dynamics', 'a' * 64, shots=20)
            result, trajectory = backend.run(request, timeout_seconds=10)
            repeat, _ = backend.run(request, timeout_seconds=10)
            self.assertEqual(result.populations, repeat.populations)
            self.assertEqual(result.raw_record_sha256, trajectory['record_sha256'])
            pair = PairRequest('photons', request.artifact_sha256)
            bundle = link_experiments(pair, optical.sample(pair), request, result)
            self.assertEqual(bundle['cold_atoms']['result']['evidence'], 'SIMULATED')
            self.assertEqual(bundle['cross_backend_parity'], 'NOT_TESTED')
            for shot in result.populations:
                self.assertEqual(shot.mode_0 + shot.mode_1, 500)
            with self.assertRaises(TimeoutError):
                backend.run(request, timeout_seconds=1e-12)
            backend.close()
            backend.close()
            with self.assertRaises(RuntimeError):
                backend.sample(request)
            clock.read()
        finally:
            backend.close()
            optical.close()
            clock.close()

    def test_cli_and_import_isolation(self):
        code = ('import motionbricks.bec_dynamics; import sys; '
                'assert not any(m in sys.modules for m in ["warp","tensorrt","onnxruntime","jax"])')
        subprocess.run([sys.executable, '-c', code], check=True)
        p = subprocess.run([sys.executable, '-m', 'motionbricks.bec_dynamics',
                            '--duration', '.1', '--samples', '3', '--compare'],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)['evidence'], 'NUMERICAL_SIMULATION')


if __name__ == '__main__':
    unittest.main()
