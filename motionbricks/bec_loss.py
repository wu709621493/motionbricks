"""Finite two-mode atom-loss/replenishment study; idealized CPU channels only."""
from __future__ import annotations
from dataclasses import asdict, replace
import math
import os
import platform
import hashlib
from pathlib import Path
import numpy as np
from scipy.linalg import eigh_tridiagonal, eigvalsh
from scipy.sparse import diags
from scipy.sparse.linalg import expm_multiply
from scipy.special import gammaln
from .bec_dynamics import Parameters, evolve, record


def atom_number(n):
    if type(n) is not int or not 1 <= n <= 500:
        raise ValueError('atom number must be an integer in [1,500]')


def operator(n, p):
    atom_number(n)
    x = np.arange(n + 1, dtype=float)
    diagonal = p.interaction * (x - n/2)**2 + p.bias * (x - n/2)
    off = -p.tunnelling * np.sqrt((x[:-1] + 1) * (n - x[:-1]))
    return diags([off, diagonal, off], [-1, 0, 1], format='csr')


def coherent(n, phase, imbalance=0):
    atom_number(n)
    if not math.isfinite(phase) or not -1 <= imbalance <= 1:
        raise ValueError('invalid initial state')
    probability = (1 + imbalance) / 2
    if probability in (0, 1):
        result = np.zeros(n + 1, complex)
        result[n if probability else 0] = 1
        return result
    x = np.arange(n + 1)
    logp = (gammaln(n+1)-gammaln(x+1)-gammaln(n-x+1)
            + x*np.log(probability)+(n-x)*np.log1p(-probability))
    result = np.exp(logp/2 + 1j*x*phase)
    return result / np.linalg.norm(result)


def spectrum(n, p):
    h = operator(n, p)
    return eigh_tridiagonal(h.diagonal(), h.diagonal(1))


def vector_evolve(state, eigensystem, duration):
    e, v = eigensystem
    return v @ (np.exp(-1j*e*duration)*(v.T @ state))


def density_evolve(rho, eigensystem, duration):
    e, v = eigensystem
    phases = np.exp(-1j*e*duration)
    transformed = v.T @ rho @ v
    return v @ (phases[:, None]*transformed*phases.conj()[None, :]) @ v.T


def density_quality(rho):
    if (not isinstance(rho, np.ndarray) or rho.ndim != 2 or rho.shape[0] != rho.shape[1]
            or not 1 <= rho.shape[0] <= 501 or not np.isfinite(rho).all()):
        raise ValueError('invalid density matrix')
    trace_error = float(abs(np.trace(rho)-1))
    hermitian_error = float(np.max(abs(rho-rho.conj().T)))
    minimum = float(eigvalsh((rho+rho.conj().T)/2, subset_by_index=[0, 0])[0])
    if trace_error > 1e-8 or hermitian_error > 1e-8 or minimum < -1e-8:
        raise ValueError('density matrix failed trace/Hermiticity/positivity checks')
    return {'trace_error': trace_error, 'hermitian_error': hermitian_error, 'minimum_eigenvalue': minimum}


def _shape(rho, minimum):
    if (not isinstance(rho, np.ndarray) or rho.ndim != 2 or rho.shape[0] != rho.shape[1]
            or not minimum <= rho.shape[0] <= 501 or not np.isfinite(rho).all()):
        raise ValueError('invalid channel input shape/values')


def remove_one(rho):
    """CPTP fixed-count, unobserved mode-blind loss: sum a_i rho a_i^dagger/N.

    Caller validates the input density once; this linear map also accepts matrix
    units for independent channel tests. No renormalization or mode postselection.
    """
    _shape(rho, 2)
    n = len(rho)-1
    x = np.arange(n)
    w0, w1 = np.sqrt(x+1), np.sqrt(n-x)
    return (w0[:, None]*rho[1:, 1:]*w0[None, :]
            + w1[:, None]*rho[:-1, :-1]*w1[None, :])/n


def add_one_isotropic(rho):
    """Idealized CPTP addition: sum a_i^dagger rho a_i/(N+2).

    Bosonically weighted mode-unresolved injection, NOT the inverse of loss or
    a device-level loading model. Real injection needs a reservoir/control model.
    """
    _shape(rho, 1)
    n = len(rho)-1
    if n >= 500:
        raise ValueError('addition exceeds 500-atom study limit')
    x = np.arange(n+1)
    w0, w1 = np.sqrt(x+1), np.sqrt(n-x+1)
    result = np.zeros((n+2, n+2), complex)
    result[1:, 1:] += w0[:, None]*rho*w0[None, :]
    result[:-1, :-1] += w1[:, None]*rho*w1[None, :]
    return result/(n+2)


def summary(rho):
    quality = density_quality(rho)
    n = len(rho)-1
    if n == 0:
        raise ValueError('vacuum has no normalized imbalance/coherence')
    x = np.arange(n+1)
    difference = 2*x-n
    probabilities = rho.diagonal().real
    mean = float(probabilities @ difference)
    correlation = np.sum(np.sqrt((x[:-1]+1)*(n-x[:-1])) * np.diag(rho, 1))
    return dict(quality, atoms=n, imbalance=mean/n,
                number_difference_variance=float(probabilities @ (difference-mean)**2),
                first_order_coherence=float(2*abs(correlation)/n),
                purity=float(np.real(np.sum(rho*rho.T))))


def distinguish(a, b):
    if a.shape != b.shape:
        raise ValueError('cannot compare different particle-number sectors')
    tv = float(np.sum(abs(a.diagonal().real-b.diagonal().real))/2)
    delta = a-b
    distance = float(np.sum(abs(eigvalsh((delta+delta.conj().T)/2)))/2)
    if tv > distance + 1e-8 or distance > 1 + 1e-8:
        raise RuntimeError('invalid distinguishability')
    return {'number_readout_tv': tv, 'ideal_equal_prior_success': (1+tv)/2,
            'quantum_trace_distance': distance}


def accuracy_audit(p=Parameters()):
    if p.initial_state != 'coherent' or p.samples > 501:
        raise ValueError('audit requires coherent initial state and at most 501 output times')
    sparse = evolve(p)
    eigensystem = spectrum(500, p)
    spectral = np.array([vector_evolve(coherent(500, p.phase, p.imbalance), eigensystem, t)
                         for t in sparse.times])
    fine = evolve(replace(p, samples=2*p.samples-1))
    maximum_error = float(np.max(np.linalg.norm(sparse.states-spectral, axis=1)))
    grid_error = float(np.max(np.linalg.norm(sparse.states-fine.states[::2], axis=1)))
    probability_error = float(np.max(abs(abs(sparse.states)**2-abs(spectral)**2)))
    if max(maximum_error, grid_error) > 1e-8:
        raise RuntimeError('independent solver/output-grid audit failed')
    return {'atoms': 500, 'dimension': 501, 'max_state_l2_error_vs_spectral': maximum_error,
            'max_probability_abs_error_vs_spectral': probability_error,
            'max_state_l2_error_vs_doubled_output_grid': grid_error,
            'max_norm_error': sparse.report['max_norm_error'],
            'max_energy_error_over_hbar': sparse.report['max_energy_error_over_hbar'],
            'tolerance_state_l2': 1e-8, 'software': sparse.report['software'],
            'physical_model_error': 'UNQUANTIFIED_WITHOUT_TRAP_OR_EXPERIMENT_DATA',
            'accuracy_meaning': 'finite-model numerical consistency, not 500 qubits or hardware accuracy'}


def study(p=Parameters(), removed_counts=(0, 1, 5, 10, 25, 50, 100, 250), event_fraction=.5):
    if p.initial_state != 'coherent' or p.phase == 0:
        raise ValueError('study requires coherent states with nonzero phase')
    if (type(event_fraction) not in (int, float) or not math.isfinite(event_fraction)
            or not 0 <= event_fraction <= 1):
        raise ValueError('invalid event fraction')
    if (not removed_counts or len(removed_counts)>20 or any(type(k) is not int or not 0 <= k < 500
            for k in removed_counts) or len(set(removed_counts)) != len(removed_counts)):
        raise ValueError('invalid removed_counts')
    audit = accuracy_audit(p)
    before, after = p.duration*event_fraction, p.duration*(1-event_fraction)
    es500 = spectrum(500, p)
    initial = [coherent(500, phase, p.imbalance) for phase in (abs(p.phase), -abs(p.phase))]
    midpoint = [vector_evolve(s, es500, before) for s in initial]
    ideal_final = [vector_evolve(s, es500, p.duration) for s in initial]
    original_distance = float(np.sqrt(max(0, 1-abs(np.vdot(*initial))**2)))
    current = [np.outer(s,s.conj()) for s in midpoint]
    previous = 0
    rows = []
    fresh = []
    for removed in sorted(removed_counts):
        for _ in range(removed-previous):
            current = [remove_one(r) for r in current]
        previous = removed
        remaining = 500-removed
        es = spectrum(remaining, p)
        lost_final = [density_evolve(r, es, after) for r in current]
        loss_metric = distinguish(*lost_final)
        replenished = [r.copy() for r in current]
        for _ in range(removed):
            replenished = [add_one_isotropic(r) for r in replenished]
        replaced_final = [density_evolve(r, es500, after) for r in replenished]
        replace_metric = distinguish(*replaced_final)
        if (loss_metric['quantum_trace_distance'] > original_distance+1e-8
                or replace_metric['quantum_trace_distance'] > loss_metric['quantum_trace_distance']+1e-8):
            raise RuntimeError('CPTP information-contraction check failed')
        rows.append({'removed': removed, 'remaining': remaining,
                     'loss': dict(loss_metric, positive_phase=summary(lost_final[0]),
                                  negative_phase_quality=density_quality(lost_final[1])),
                     'replace_isotropic': dict(replace_metric, positive_phase=summary(replaced_final[0]),
                        negative_phase_quality=density_quality(replaced_final[1]),
                        fidelity_to_no_loss_positive=float(np.real(np.vdot(ideal_final[0], replaced_final[0] @ ideal_final[0]))))})
        # Newly prepared smaller systems are a separate experiment, not a loss channel.
        for policy in ('fixed_U', 'fixed_UN'):
            q = p if policy == 'fixed_U' else replace(p, interaction=p.interaction*500/remaining)
            eig = spectrum(remaining, q)
            vectors = [vector_evolve(coherent(remaining, phase, p.imbalance), eig, p.duration)
                       for phase in (abs(p.phase), -abs(p.phase))]
            densities = [np.outer(v,v.conj()) for v in vectors]
            fresh.append({'atoms':remaining, 'coupling_policy':policy, 'interaction':q.interaction,
                          **distinguish(*densities)})
    return record({'schema_version':1,'evidence':'NUMERICAL_SIMULATION', 'parameters':asdict(p),
                   'event_fraction':event_fraction,'event_time_seconds':before,
                   'loss_model':'fixed-count mode-blind loss at one instant; no waiting-time dynamics',
                   'addition_model':'idealized isotropic CPTP injection; not inverse loss',
                   'accuracy':audit,'original_quantum_trace_distance':original_distance,
                   'provenance': {'platform': platform.platform(), 'architecture': platform.machine(),
                     'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                     'dynamics_source_sha256': hashlib.sha256(Path(__file__).with_name('bec_dynamics.py').read_bytes()).hexdigest(),
                     'OPENBLAS_NUM_THREADS': os.environ.get('OPENBLAS_NUM_THREADS'),
                     'OMP_NUM_THREADS': os.environ.get('OMP_NUM_THREADS')},
                   'event_study':rows,'fresh_preparation_sweep':fresh,
                   'hardware_validation':'NOT_PERFORMED','memory_retrieval':'NOT_IMPLEMENTED',
                   'quantum_advantage':'NOT_TESTED'})
