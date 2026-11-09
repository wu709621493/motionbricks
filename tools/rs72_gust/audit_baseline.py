"""Independent algebra and execution of the pinned, unchanged RS-72 functions."""
import hashlib
import json
import math
from pathlib import Path
import platform

import numpy as np
from motionbricks.rs72 import Aircraft, gust_case

ROOT = Path(__file__).resolve().parents[2]


def require(condition, message='independent static audit mismatch'):
    if not condition:
        raise ValueError(message)


def audit():
    paths = ('motionbricks/rs72.py', 'docs/results/rs72/report.json')
    files = []
    for path in paths:
        data = (ROOT / path).read_bytes()
        files.append({'path': path, 'git_blob_sha': hashlib.sha1(
            f'blob {len(data)}\0'.encode() + data).hexdigest()})
    provenance = {'reference_commit': 'c4754016b9e615805b425594a7ec30aba768f6e0',
                  'current_files': files}
    if files[1]['git_blob_sha'] != '5f93c71f0c2bdada74da244d926054b1b58d02fd':
        raise ValueError('archived RS-72 report differs from the reviewed baseline')
    archived = json.loads((ROOT / paths[1]).read_text())
    a = Aircraft()
    rows = []
    for old in archived['gust_cases']:
        v, u = old['tas_m_s'], old['vertical_gust_m_s']
        # Separate implementation: directly construct total uniform load from
        # trim + incremental lift, then integrate its first moment analytically.
        cl = 2 * 12000 * 9.80665 / (1.2 * v*v * 70) + 4.8 * u/v
        total_lift = 12000 * 9.80665 + .5 * 1.2 * v * 70 * 4.8 * u
        line_load = total_lift / 24
        moment = line_load * 12**2 / 2
        stress_mpa = abs(moment) * .3 / .0013 / 1e6
        tip = line_load * 12**4 / (8 * 70e9 * .0013)
        k_trial = 1.12 * stress_mpa * math.sqrt(math.pi * .002)
        now = gust_case(v, u, a)
        for key, value in [('cl_linear_trial', cl), ('elastic_trial_stress_mpa', stress_mpa),
                           ('tip_deflection_m', tip), ('root_moment_nm', moment)]:
            require(math.isclose(now[key], value, rel_tol=1e-12, abs_tol=1e-12), key)
            require(math.isclose(old[key], value, rel_tol=1e-12, abs_tol=1e-12), key)
        small_angle = abs(u/v) > .1
        cl_limit = abs(cl) > 1.8
        strength = [name for name, trigger in [('yield', stress_mpa > 250),
                    ('ultimate_1_5x_load', 1.5 * stress_mpa > 400),
                    ('fracture', k_trial > 30)] if trigger]
        deformation = abs(tip) > .6
        require(set(now['exceeded_screens']) == set(strength + (['elastic_deflection'] if deformation else [])))
        require(now['model_flags'] == (['small_angle_screen_exceeded'] if small_angle else []) + (['assumed_lift_coefficient_screen_exceeded'] if cl_limit else []))
        rows.append({'tas_m_s':v, 'gust_m_s':u, 'ratio_abs':abs(u/v), 'cl_trial':cl,
                     'stress_mpa':stress_mpa, 'tip_m':tip, 'k_trial_mpa_sqrt_m':k_trial,
                     'small_angle_exceeded':small_angle, 'cl_exceeded':cl_limit,
                     'strength_flags':strength, 'deflection_exceeded':deformation})
    return {'base':provenance, 'python':platform.python_version(), 'numpy':np.__version__,
            'execution_scope':'original gust_case and beam_case; renderer and historical CI not rerun',
            'case_count':len(rows), 'small_angle_count':sum(r['small_angle_exceeded'] for r in rows),
            'cl_count':sum(r['cl_exceeded'] for r in rows),
            'strength_count':sum(bool(r['strength_flags']) for r in rows), 'cases':rows,
            'unknown_slots':[{'id':'U01','status':'UNSPECIFIED','value':None},
                             {'id':'U02','status':'UNSPECIFIED','value':None}]}


if __name__ == '__main__':
    print(json.dumps(audit(), indent=2, ensure_ascii=False, allow_nan=False))
