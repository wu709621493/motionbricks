"""Reproduce committed offline controls without GPU/SDK/third-party dependencies."""
from dataclasses import asdict
import argparse
import json
import hashlib
from pathlib import Path
import platform
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from motionbricks.bell_chsh import (CHSHRequest, Simulation, SimulatedCHSHSampler,
                                   report, digest)
from motionbricks.optical_quantum import SimulatedClock

SCENARIOS = {
    'clean': {},
    'flip_10pct': {'flip_probability': .1},
    'flip_50pct': {'flip_probability': .5},
    'loss_20pct': {'loss_probability': .2},
    'loss_100pct': {'loss_probability': 1.},
    'selective_100pct': {'selective_rejection': 1.},
    'loss_and_selection': {'loss_probability': .2, 'selective_rejection': 1.},
}


def run():
    plans = [(model, n, seed, name, cfg)
             for model in ('CLASSICAL_LHV', 'IDEAL_BELL_PROBABILITY')
             for n in (100, 1000, 10000) for seed in (0, 7, 42)
             for name, cfg in SCENARIOS.items()]
    plans += [('CLASSICAL_LHV', n, seed, 'local_detection_attack',
               {'local_detection_attack': True})
              for n in (100, 1000, 10000) for seed in (0, 7, 42)]
    clock, reports = SimulatedClock(), []
    try:
        for model, n, seed, name, cfg in plans:
            req = CHSHRequest(f'{model}-{name}-n{n}-seed{seed}',
                              digest({'study': 'bell-chsh-v1'}), shots=(n,)*4,
                              alpha=.05/len(plans))
            sampler = SimulatedCHSHSampler(clock, Simulation(model=model, seed=seed, **cfg))
            try:
                reports.append({'scenario': name, 'report': report(req, sampler.sample(req))})
            finally:
                sampler.close()
        # Unselected small-sample distribution: show EVERY seed, no best-seed search.
        small = []
        for seed in range(200):
            req = CHSHRequest(f'small-{seed}', digest({'study': 'bell-chsh-v1'}), shots=(20,)*4)
            sampler = SimulatedCHSHSampler(clock, Simulation(seed=seed))
            try:
                r = report(req, sampler.sample(req))
                small.append({'seed': seed, 'statistics': r['primary_all_trials_no_click_plus_one'],
                              'record_sha256': r['record_sha256']})
            finally:
                sampler.close()
    finally:
        clock.close()
    payload = {'schema_version': 1, 'evidence': 'OFFLINE_SIMULATIONS_ONLY',
               'python': platform.python_version(),
               'source_sha256': {name: hashlib.sha256((Path(__file__).resolve().parents[2]/name).read_bytes()).hexdigest()
                                 for name in ('motionbricks/bell_chsh.py', 'tools/bell_chsh/run_study.py')},
               'study_family_size': len(plans),
               'family_alpha': .05, 'multiplicity': 'Bonferroni over 135 primary intervals',
               'reports': reports, 'small_sample_exploratory': small,
               'small_sample_S_gt_2': sum(v['statistics']['signed_S'] > 2 for v in small),
               'small_sample_95pct_excludes_local': sum(
                   v['statistics']['interval_excludes_local_range'] for v in small)}
    return dict(payload, study_sha256=digest(payload))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'path': str(args.output), 'reports': len(result['reports']),
                      'study_sha256': result['study_sha256'],
                      'small_sample_S_gt_2': result['small_sample_S_gt_2'],
                      'small_sample_95pct_excludes_local': result['small_sample_95pct_excludes_local']}))
