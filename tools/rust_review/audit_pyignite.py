"""Run every existing PyIgnite parity fixture, preserving failures and tolerances."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[2]
import numpy as np
import torch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    args = parser.parse_args()
    source_root = args.source_root.resolve()
    sys.path.insert(0, str(source_root / 'tools/pyignite'))
    import validate
    cases = []
    def check(name, native_fn, oracle_fn):
        with torch.inference_mode():
            actual = native_fn()
            reference = oracle_fn().numpy()
        error = np.abs(actual.astype(np.float64) - reference)
        violations = error > 2e-5 + 2e-5 * np.abs(reference.astype(np.float64))
        repeated = all(np.array_equal(actual, native_fn()) for _ in range(10))
        cases.append({'name': name, 'status': 'PASS' if not violations.any() and repeated else 'FAIL',
                      'max_abs_error': float(error.max()), 'violations': int(violations.sum()),
                      'elements': int(error.size), 'repeat_identical': repeated,
                      'actual_sha256': hashlib.sha256(actual.tobytes()).hexdigest(),
                      'reference_sha256': hashlib.sha256(reference.tobytes()).hexdigest(),
                      'violations_sha256': hashlib.sha256(violations.tobytes()).hexdigest()})
    for n, d in [(1, 2), (17, 32), (256, 512), (4096, 64)]:
        check(f'PE-{n}-{d}', lambda: validate.PE1d_sincos(n, d),
              lambda: validate.upstream.PE1d_sincos(n, d))
    for depth, width, si, so, shape, dropout in [
            (1, 8, 3, 2, (3,), 0), (2, 32, 7, 5, (4, 7), 0.3),
            (3, 64, 16, 9, (2, 11, 16), 0), (2, 256, 128, 64, (32, 128), 0)]:
        model, native, x = validate.fixture(depth, width, si, so, shape, dropout)
        tx = torch.from_numpy(x)
        check(f'FC-{depth}-{width}-{shape}', lambda: native(x), lambda: model(tx))
    report = {'status': 'PASS' if all(c['status'] == 'PASS' for c in cases) else 'FAIL',
              'python': platform.python_version(), 'numpy': np.__version__, 'torch': torch.__version__,
              'platform': platform.platform(), 'atol': 2e-5, 'rtol': 2e-5,
              'source_sha256': {name: hashlib.sha256((source_root / name).read_bytes()).hexdigest()
                                for name in ['tools/pyignite/kernels.cpp', 'tools/pyignite/pyignite/__init__.py',
                                             'tools/pyignite/validate.py', 'tools/onnx/models/layers.py']},
              'cases': cases, 'note': 'Existing fixtures/tolerances unchanged; every case evaluated.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f'{report["status"]}: {sum(c["status"] == "PASS" for c in cases)}/8 cases; {args.output}')
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
