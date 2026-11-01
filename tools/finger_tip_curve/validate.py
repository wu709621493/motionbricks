"""Reproduce fixture diagnostics and a seed sweep; not probability calibration."""
import json
import platform
from pathlib import Path
import numpy as np
from curve_inference import infer_curve
from synthetic import cases


def report():
    rows = []
    for seed in range(100, 120):
        for name, case in cases(seed).items():
            r = infer_curve(case['request'])
            rows.append(dict(seed=seed, case=name, expected_status=case['expected_status'],
                             status=r['status'], expected_model=case['expected_model'], model=r['model_family']))
    matches = sum(r['status'] == r['expected_status'] and r['model'] == r['expected_model'] for r in rows)
    false_acceptances = [r for r in rows if r['status']=='accepted' and (r['expected_status']!='accepted' or r['model']!=r['expected_model'])]
    return dict(python=platform.python_version(), numpy=np.__version__, seed_range=[100,119],
                total=len(rows), expected_outcome_matches=matches, false_acceptances=false_acceptances,
                mismatches=[r for r in rows if r['status']!=r['expected_status'] or r['model']!=r['expected_model']],
                calibration='none; synthetic engineering checks only', rows=rows)


if __name__ == '__main__':
    r = report()
    Path(__file__).with_name('validation_results.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({k:v for k,v in r.items() if k!='rows'},indent=2))
