"""Classical Hopfield ablation control; not a BEC/qubit implementation."""
from __future__ import annotations
import hashlib
from pathlib import Path
import numpy as np
from .bec_dynamics import record


def hebbian(patterns):
    x = np.asarray(patterns, dtype=float)
    if x.ndim != 2 or not x.size or not np.isin(x, [-1, 1]).all():
        raise ValueError('patterns must be a nonempty matrix of +/-1')
    w = x.T @ x / x.shape[1]
    np.fill_diagonal(w, 0)
    return w


def recall(weights, cue, seed=0, max_sweeps=50):
    w, state = np.asarray(weights, dtype=float), np.array(cue, dtype=float, copy=True)
    if (w.shape != (len(state), len(state)) or state.ndim != 1 or not len(state)
            or not np.isfinite(w).all() or not np.isin(state, [-1, 1]).all()
            or not np.allclose(w, w.T, atol=1e-14, rtol=0)
            or not np.allclose(w.diagonal(), 0, atol=1e-14, rtol=0)):
        raise ValueError('require symmetric zero-diagonal weights and binary cue')
    if type(max_sweeps) is not int or max_sweeps < 1:
        raise ValueError('max_sweeps must be positive')
    rng = np.random.default_rng(seed)
    field = w @ state
    energies = [float(-.5*state @ field)]
    for sweep in range(max_sweeps):
        changed = False
        for i in rng.permutation(len(state)):
            new = 1 if field[i] > 1e-12 else (-1 if field[i] < -1e-12 else state[i])
            if new != state[i]:
                delta = new-state[i]
                state[i] = new
                field += w[:, i]*delta
                changed = True
        energy = float(-.5*state @ (w @ state))
        if energy > energies[-1]+1e-8:
            raise RuntimeError('Hopfield energy increased')
        energies.append(energy)
        if not changed:
            return state, energies, True
    return state, energies, False


def ablation_study(seed=20261101):
    n, stored, cues_per_pattern = 500, 20, 3
    rng = np.random.default_rng(seed)
    patterns = rng.choice([-1, 1], size=(stored, n))
    weights = hebbian(patterns)
    order = rng.permutation(n)
    tasks = []
    for target in range(stored):
        for repeat in range(cues_per_pattern):
            cue = patterns[target].copy()
            cue[rng.choice(n, size=50, replace=False)] *= -1
            tasks.append((target, cue, rng.choice([-1, 1], size=n), seed+target*10+repeat))
    rows = []
    for keep in (500, 450, 400, 250, 100, 50):
        indices = order[:keep]
        smaller = weights[np.ix_(indices, indices)]  # Original synapses, no retraining.
        exact, bit_scores, restored, full_scores, converged = [], [], [], [], []
        for target, cue, replacement, task_seed in tasks:
            state, _, done = recall(smaller, cue[indices], task_seed)
            expected = patterns[target, indices]
            exact.append(bool(np.array_equal(state, expected)))
            bit_scores.append(float(np.mean(state == expected)))
            converged.append(done)
            # Restore original synapses; missing node values initialized randomly.
            full = replacement.copy()
            full[indices] = state
            recovered, _, done_full = recall(weights, full, task_seed)
            restored.append(bool(np.array_equal(recovered, patterns[target])))
            full_scores.append(float(np.mean(recovered == patterns[target])))
            if not done_full:
                raise RuntimeError('replacement control did not converge')
        rows.append({'remaining_nodes':keep, 'stored_patterns':stored, 'nominal_load':stored/keep,
                     'trials':len(tasks), 'surviving_exact_recall_count':sum(exact),
                     'surviving_mean_bit_accuracy':float(np.mean(bit_scores)),
                     'converged_trials':sum(converged),
                     'restored_exact_recall_count':sum(restored),
                     'restored_mean_bit_accuracy':float(np.mean(full_scores))})
    return record({'schema_version':1,'evidence':'CLASSICAL_SIMULATION','seed':seed,
                   'nodes':n,'stored_patterns':stored,'initial_flips':50,'rows':rows,
                   'numpy':np.__version__, 'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   'caveat':'60 fixed correlated cues; descriptive results, not independent confidence intervals',
                   'replacement_assumption':'original weights restored; missing spin values randomized',
                   'bec_equivalence':'NOT_ESTABLISHED'})
