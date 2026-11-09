"""Bounded 25-record illustrative sensitivity; not an aircraft envelope."""
import argparse
import json
from pathlib import Path

import numpy as np
from motionbricks.rs72_gust import Case, convergence


def run(out_dir):
    target = Path(out_dir)
    if target.exists():
        raise FileExistsError('output directory already exists')
    cases = [('H_grid', Case(gradient_m=float(h))) for h in np.linspace(9.144, 106.68, 16)]
    cases += [('mass_damping', Case(wing_half_mass_kg=m, damping_ratio=z))
              for m in (600., 1200., 2400.) for z in (.01, .02, .05)]
    rows = []
    for group, case in cases:
        runs, check = convergence(case)
        rows.append({'group': group, 'summary': runs[-1][4], 'convergence': check})
    result = {'status': 'ILLUSTRATIVE_SENSITIVITY', 'cases': rows,
              'all_time_grids_converged': all(r['convergence']['numerics_status'] == 'CONVERGED' for r in rows),
              'gradient_grid_refinement_completed': False,
              'all_airspeeds_and_signed_gusts_swept': False,
              'airworthiness_demonstrated': False, 'flight_release': False}
    encoded = json.dumps(result, indent=2, allow_nan=False)
    target.mkdir(parents=True, exist_ok=False)
    with (target / 'sensitivity.json').open('x', encoding='utf-8') as handle:
        handle.write(encoded + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', required=True)
    args = parser.parse_args()
    try:
        report = run(args.out_dir)
        print(json.dumps(report, indent=2, allow_nan=False))
        if not report['all_time_grids_converged']:
            raise SystemExit(2)
    except (ValueError, OSError) as exc:
        parser.exit(1, f'RS-72 sensitivity refused: {exc}\n')
