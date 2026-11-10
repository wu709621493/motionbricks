"""Gate unrelated integration on no new regression; retain strict parity failures.

Only PE-4096-64 may be an existing failure, and only with identical output,
oracle, violation mask and numerical statistics in a freshly built fixed base.
"""
import argparse
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASELINE = '65fa0a160946ddbb3d196f552a0a13fe63432fcf'
KNOWN = 'PE-4096-64'
EXPECTED = {'PE-1-2', 'PE-17-32', 'PE-256-512', KNOWN,
            'FC-1-8-(3,)', 'FC-2-32-(4, 7)', 'FC-3-64-(2, 11, 16)', 'FC-2-256-(32, 128)'}


def assess(base, current):
    for report in [base, current]:
        cases = report['cases']
        assert len(cases) == len(EXPECTED) and {c['name'] for c in cases} == EXPECTED, 'missing/duplicate cases'
        assert report['atol'] == report['rtol'] == 2e-5, 'tolerance changed'
        for case in cases:
            assert case['status'] in {'PASS', 'FAIL'} and case['repeat_identical'], 'invalid or unstable result'
            assert case['elements'] > 0 and math.isfinite(case['max_abs_error']), 'invalid numeric result'
            assert (case['status'] == 'PASS') == (case['violations'] == 0), 'inconsistent result'
        failed = any(c['status'] == 'FAIL' for c in cases)
        assert report['status'] == ('FAIL' if failed else 'PASS'), 'inconsistent summary'
    for key in ['python', 'numpy', 'torch', 'platform']:
        assert base[key] == current[key], f'environment changed: {key}'
    original = {c['name']: c for c in base['cases']}
    assert all(c['name'] == KNOWN or c['status'] == 'PASS' for c in base['cases']), 'unexpected baseline failure'
    known_failures = []
    for case in current['cases']:
        if case['status'] == 'PASS':
            continue
        assert case['name'] == KNOWN and original[KNOWN]['status'] == 'FAIL', 'new parity failure'
        assert case == original[KNOWN], 'known failure changed: outputs/mask/stats differ'
        known_failures.append(KNOWN)
    return {'status': 'PASS_NO_NEW_REGRESSION', 'strict_current_parity': current['status'],
            'known_parity_failures': known_failures,
            'note': 'No-new-regression gate; a retained FAIL is not a numerical parity pass.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    audit = ROOT / 'tools/rust_review/audit_pyignite.py'
    report = {'status': 'FAIL', 'baseline_commit': BASELINE}
    def run_audit(source, name):
        build = subprocess.run([sys.executable, str(source / 'tools/pyignite/build.py')],
                               cwd=source, capture_output=True, text=True, timeout=120)
        (out / f'{name}-build.txt').write_text(build.stdout + build.stderr)
        build.check_returncode()
        path = out / f'{name}-strict-parity.json'
        path.unlink(missing_ok=True)  # A crashed audit must not reuse an older result.
        result = subprocess.run([sys.executable, str(audit), '--source-root', str(source), '--output', str(path)],
                                capture_output=True, text=True, timeout=120)
        (out / f'{name}-audit.txt').write_text(result.stdout + result.stderr)
        assert result.returncode in (0, 1) and path.exists(), f'{name} audit did not produce a result'
        data = json.loads(path.read_text())
        assert result.returncode == (0 if data['status'] == 'PASS' else 1), 'unexpected audit exit'
        return data
    try:
        # Fetch-depth 0 in CI makes the pinned base available; never silently use another ref.
        archive = subprocess.check_output(['git', 'archive', BASELINE, 'tools/pyignite', 'tools/onnx/models/layers.py'],
                                          cwd=ROOT, timeout=30)
        with tempfile.TemporaryDirectory() as folder:
            base_root = Path(folder)
            with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
                bundle.extractall(base_root, filter='data')
            base = run_audit(base_root, 'baseline')
            current = run_audit(ROOT, 'current')
            report.update(assess(base, current))
            report['baseline_source_sha256'] = base['source_sha256']
            report['current_source_sha256'] = current['source_sha256']
    except (AssertionError, KeyError, ValueError, OSError, subprocess.SubprocessError) as exc:
        report['error'] = str(exc)
    (out / 'regression.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'PASS_NO_NEW_REGRESSION' else 1


if __name__ == '__main__':
    raise SystemExit(main())
