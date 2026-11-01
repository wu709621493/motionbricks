"""Fixed-N two-mode quantum dynamics on CPU; numerical simulation, not hardware."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
import platform
import time

import numpy as np
import scipy
from scipy.sparse import diags
from scipy.sparse.linalg import expm_multiply
from scipy.special import gammaln

from .cold_atoms import BECRequest, BECResult, PopulationShot
from .optical_quantum import OpticalClock

N = 500
DIMENSION = N + 1
NORM_TOLERANCE = 1e-8
ENERGY_RELATIVE_TOLERANCE = 1e-8


def record(payload):
    data = json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return dict(payload, record_sha256=hashlib.sha256(data).hexdigest())


@dataclass(frozen=True)
class Parameters:
    # H/hbar = -J(a0^dagger a1 + a1^dagger a0) + U*m^2 + bias*m,
    # m = (n0-n1)/2. All coefficients in radians/second; time in seconds.
    tunnelling: float = 1.0
    interaction: float = 0.002
    bias: float = 0.0
    duration: float = 1.0
    samples: int = 21
    initial_state: str = 'coherent'
    imbalance: float = 0.0
    phase: float = 0.1
    fock_n0: int = 250

    def __post_init__(self):
        for name in ('tunnelling', 'interaction', 'bias', 'duration', 'imbalance', 'phase'):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f'{name} must be a finite real number')
        if not -math.pi <= self.phase <= math.pi:
            raise ValueError('phase must be in [-pi,pi] radians')
        if self.duration <= 0 or not -1 <= self.imbalance <= 1:
            raise ValueError('duration must be positive; imbalance must be in [-1,1]')
        if type(self.samples) is not int or not 2 <= self.samples <= 1001:
            raise ValueError('samples must be an integer in [2,1001]')
        if self.initial_state not in ('coherent', 'fock'):
            raise ValueError('initial_state must be coherent or fock')
        if type(self.fock_n0) is not int or not 0 <= self.fock_n0 <= N:
            raise ValueError('fock_n0 must be an integer in [0,500]')
        if self.action_bound > 20000:
            raise ValueError('software work limit exceeded: duration * Hamiltonian bound > 20000')

    @property
    def action_bound(self):
        return self.duration * (N * abs(self.tunnelling) + N**2 / 4 * abs(self.interaction)
                                + N / 2 * abs(self.bias))


def hamiltonian(p: Parameters):
    n = np.arange(DIMENSION, dtype=float)
    m = n - N / 2
    coupling = -p.tunnelling * np.sqrt((n[:-1] + 1) * (N - n[:-1]))
    return diags([coupling, p.interaction * m**2 + p.bias * m, coupling], [-1, 0, 1], format='csr')


def initial_vector(p: Parameters):
    state = np.zeros(DIMENSION, dtype=np.complex128)
    if p.initial_state == 'fock':
        state[p.fock_n0] = 1
        return state
    probability = (1 + p.imbalance) / 2
    if probability in (0, 1):
        state[N if probability == 1 else 0] = 1
        return state
    n = np.arange(DIMENSION)
    log_p = (gammaln(N + 1) - gammaln(n + 1) - gammaln(N - n + 1)
             + n * np.log(probability) + (N - n) * np.log1p(-probability))
    state = np.exp(log_p / 2 + 1j * n * p.phase)
    return state / np.linalg.norm(state)  # Normalize prepared input, never evolved output.


@dataclass
class Evolution:
    parameters: Parameters
    times: np.ndarray
    states: np.ndarray
    report: dict


def evolve(p: Parameters) -> Evolution:
    if not isinstance(p, Parameters):
        raise ValueError('expected Parameters')
    h = hamiltonian(p)
    initial = initial_vector(p)
    times = np.linspace(0, p.duration, p.samples)
    start = time.perf_counter()
    states = expm_multiply(-1j * h, initial, start=0, stop=p.duration, num=p.samples,
                          endpoint=True, traceA=-1j * h.diagonal().sum())
    seconds = time.perf_counter() - start
    if states.shape != (p.samples, DIMENSION) or not np.isfinite(states).all():
        raise RuntimeError('invalid or nonfinite evolved states')
    probabilities = np.abs(states)**2
    norms = probabilities.sum(axis=1)
    energies = np.real(np.sum(states.conj() * (h @ states.T).T, axis=1))
    norm_error = float(np.max(np.abs(norms - 1)))
    energy_scale = max(1.0, float(np.max(np.asarray(abs(h).sum(axis=1)))))
    energy_error = float(np.max(np.abs(energies - energies[0])))
    if norm_error > NORM_TOLERANCE or energy_error / energy_scale > ENERGY_RELATIVE_TOLERANCE:
        raise RuntimeError('numerical conservation check failed; output was not renormalized')
    n = np.arange(DIMENSION)
    difference = 2 * n - N
    mean = probabilities @ difference
    variance = np.sum(probabilities * (difference[None, :] - mean[:, None])**2, axis=1)
    hopping = np.sqrt((n[:-1] + 1) * (N - n[:-1]))
    coherence = 2 * np.abs(np.sum(states[:, 1:].conj() * states[:, :-1] * hopping, axis=1)) / N
    result = record({
        'schema_version': 1, 'evidence': 'NUMERICAL_SIMULATION', 'device': 'CPU',
        'model': 'fixed-N-two-mode-bose-hubbard-v1', 'atom_count': N, 'dimension': DIMENSION,
        'parameters': asdict(p), 'basis': '|n0,500-n0>, n0=0..500',
        'coefficient_units': 'rad/s', 'time_units': 's',
        'solver': 'scipy.sparse.linalg.expm_multiply',
        'software': {'python': platform.python_version(), 'numpy': np.__version__, 'scipy': scipy.__version__},
        'platform': platform.platform(), 'architecture': platform.machine(), 'solve_seconds': seconds,
        'initial_state_sha256': hashlib.sha256(initial.astype('<c16').tobytes()).hexdigest(),
        'trajectory_sha256': hashlib.sha256(states.astype('<c16').tobytes()).hexdigest(),
        'times': times.tolist(), 'imbalance': (mean / N).tolist(),
        'number_difference_variance': variance.tolist(), 'first_order_coherence': coherence.tolist(),
        'energy_over_hbar': energies.tolist(), 'norms': norms.tolist(),
        'max_norm_error': norm_error, 'max_energy_error_over_hbar': energy_error,
        'energy_error_scale': energy_scale, 'norm_tolerance': NORM_TOLERANCE,
        'energy_relative_tolerance': ENERGY_RELATIVE_TOLERANCE,
        'final_population_probabilities': probabilities[-1].tolist(),
        'particle_number_conservation': 'BY_FIXED_N_BASIS',
        'condensation_verification': 'NOT_PERFORMED', 'entanglement_verification': 'NOT_PERFORMED',
        'computational_advantage': 'NOT_TESTED', 'motion_inference': 'NOT_PERFORMED',
    })
    return Evolution(p, times, states, result)


def compare_initial_states(p: Parameters):
    """Equal-prior discrimination by number readout, not learned pattern recovery.

    Compare coherent states with phase +/-abs(phase), same imbalance. Each case
    uses one common Hamiltonian for both states; unitary trace distance is conserved.
    """
    if p.initial_state != 'coherent' or p.phase == 0:
        raise ValueError('comparison requires coherent states and nonzero phase')
    cases = {}
    for label, u in (('noninteracting', 0.0), ('interacting', p.interaction)):
        a = evolve(replace(p, interaction=u, phase=abs(p.phase)))
        b = evolve(replace(p, interaction=u, phase=-abs(p.phase)))
        pa, pb = np.abs(a.states)**2, np.abs(b.states)**2
        tv = np.sum(np.abs(pa - pb), axis=1) / 2
        overlap = np.sum(a.states.conj() * b.states, axis=1)
        trace_distance = np.sqrt(np.maximum(0, 1 - np.abs(overlap)**2))
        # Compare overlap squared directly: sqrt(1-overlap^2) is ill-conditioned
        # near identical states. Conservation was already checked before this.
        if (np.max(np.abs(np.abs(overlap)**2 - abs(overlap[0])**2)) > 1e-8
                or np.max(tv - trace_distance[0]) > 1e-7):
            raise RuntimeError('distinguishability consistency check failed')
        cases[label] = {'positive_phase': a.report, 'negative_phase': b.report,
                        'number_readout_total_variation': tv.tolist(),
                        'equal_prior_single_shot_success': ((1 + tv) / 2).tolist(),
                        'pure_state_trace_distance': trace_distance.tolist(),
                        'overlap_squared': (np.abs(overlap)**2).tolist()}
    return record({'schema_version': 1, 'evidence': 'NUMERICAL_SIMULATION', 'cases': cases,
                   'task': 'two_known_initial_states_number_readout',
                   'interpretation': 'Measurement-dependent distinguishability, not increased quantum information',
                   'memory_retrieval': 'NOT_IMPLEMENTED', 'quantum_advantage': 'NOT_TESTED'})


class DynamicsBEC500:
    """Compatible ColdAtomBackend adapter; borrows clock and serializes via caller."""
    def __init__(self, clock: OpticalClock, parameters: Parameters = Parameters(), *, seed=0):
        if not isinstance(parameters, Parameters) or type(seed) is not int or not 0 <= seed < 2**64:
            raise ValueError('invalid parameters or seed')
        self.clock, self.parameters, self.seed, self.closed = clock, parameters, seed, False

    def run(self, request: BECRequest, *, timeout_seconds=1.0):
        if self.closed:
            raise RuntimeError('dynamics backend is closed')
        if not isinstance(request, BECRequest):
            raise ValueError('expected BECRequest')
        if type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError('timeout_seconds must be finite and positive')
        # A post-execution deadline rejects late results; it cannot interrupt SciPy.
        start = time.perf_counter()
        clock = self.clock.read()
        evolution = evolve(self.parameters)
        identity = json.dumps([self.seed, asdict(request), asdict(self.parameters)], sort_keys=True).encode()
        rng = np.random.default_rng(int.from_bytes(hashlib.sha256(identity).digest(), 'big'))
        probabilities = np.abs(evolution.states[-1])**2
        # Only the sampling distribution is normalized after conservation passes.
        draws = rng.choice(DIMENSION, size=request.shots, p=probabilities / probabilities.sum())
        populations = tuple(PopulationShot(N, int(n), N - int(n), 0) for n in draws)
        result = BECResult(request.request_id, request.artifact_sha256, request.species, request.operation,
                           request.preparation_id, populations, 0, clock,
                           'cpu-two-mode-bose-hubbard-v1', 'SIMULATED', evolution.report['record_sha256'])
        result.validate(request)
        if time.perf_counter() - start > timeout_seconds:
            raise TimeoutError('CPU simulation exceeded deadline; no result returned (not a hard interrupt)')
        return result, evolution.report

    def sample(self, request, *, timeout_seconds=1.0):
        return self.run(request, timeout_seconds=timeout_seconds)[0]

    def close(self):
        self.closed = True


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interaction', type=float, default=0.002)
    parser.add_argument('--tunnelling', type=float, default=1.0)
    parser.add_argument('--bias', type=float, default=0.0)
    parser.add_argument('--duration', type=float, default=1.0)
    parser.add_argument('--samples', type=int, default=21)
    parser.add_argument('--phase', type=float, default=0.1)
    parser.add_argument('--imbalance', type=float, default=0.0)
    parser.add_argument('--compare', action='store_true')
    args = parser.parse_args()
    try:
        params = Parameters(**{k: v for k, v in vars(args).items() if k != 'compare'})
        output = compare_initial_states(params) if args.compare else evolve(params).report
        print(json.dumps(output, indent=2, allow_nan=False))
        return 0
    except (ValueError, RuntimeError) as exc:
        print(json.dumps({'status': 'FAILED', 'error': str(exc)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
