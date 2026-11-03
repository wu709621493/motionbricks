"""Run from repository root: python -m tools.root_soil.run_study."""
import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path
from .model import G, Plane, displacement, screen


def study():
    rows = []
    for pressure in (0.0, 2000.0, 4000.0):
        for strength in (0.0, 1000.0, 3000.0, 6000.0):
            shallow = Plane('patch_A_depth_1m', 25, 1, 1800, 3000, 32, pressure, strength)
            deep = replace(shallow, label='patch_A_depth_2m_below_roots', thickness_m=2,
                           root_cohesion_pa=0)
            gap = replace(shallow, label='patch_B_root_gap_depth_1m', root_cohesion_pa=strength/4)
            planes = [shallow, deep, gap]
            record = [0.0]*10 + [0.45*G]*20 + [-0.2*G]*20 + [0.0]*10
            rows.append({'inputs': [asdict(p) for p in planes], 'screen': screen(planes),
                         'displacements': {p.label: displacement(p, record, 0.02) for p in planes}})
    return {'evidence': 'SYNTHETIC_UNCALIBRATED',
            'species': {'redwood': 'identity and measurements pending',
                        'small_leaf_banyan': 'identity and measurements pending'},
            'source_sha256': {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                              for name in ('model.py', 'run_study.py')},
            'input_record': {'dt_s': 0.02, 'segments_accel_g_and_samples': [[0,10],[0.45,20],[-0.2,20],[0,10]],
                             'meaning': 'signed adverse horizontal inertia; synthetic rectangular pulse'},
            'cases': rows}

if __name__ == '__main__':
    print(json.dumps(study(), indent=2, allow_nan=False))
