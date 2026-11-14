"""Strict, unchanged Torch oracle plus separately labelled PE error localization.

Missing Torch/native dependencies return NOT_RUN (exit 2), never a green result.
Controlled exp substitutions are localization only and cannot change strict status.
"""
import argparse
import ctypes
import ctypes.util
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform
import subprocess
import sys

import numpy as np

ATOL = RTOL = 2e-5
ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def comparison(actual, reference):
    finite = bool(np.isfinite(actual).all() and np.isfinite(reference).all())
    try:
        np.testing.assert_allclose(actual, reference, atol=ATOL, rtol=RTOL)
        status = 'PASS' if finite else 'FAIL'
    except AssertionError:
        status = 'FAIL'
    mask = ~np.isclose(actual, reference, atol=ATOL, rtol=RTOL, equal_nan=False)
    delta = np.abs(actual.astype(np.float64)-reference.astype(np.float64))
    return {'status': status, 'violations': int(np.count_nonzero(mask)),
            'finite': finite, 'max_abs_error': float(delta.max()) if finite else None}, mask


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--base-commit', default='not_supplied')
    args = parser.parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error('output directory must be empty; preserve previous evidence')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    sources = [ROOT/'tools/onnx/models/layers.py', ROOT/'tools/pyignite/kernels.cpp', Path(__file__)]
    report = {'schema_version': 1, 'case': 'PE-4096-64', 'base_commit': args.base_commit,
              'platform': platform.platform(), 'machine': platform.machine(), 'python': platform.python_version(),
              'numpy': np.__version__, 'atol': ATOL, 'rtol': RTOL, 'oracle_changed': False,
              'sources': {str(p.relative_to(ROOT)): sha(p) for p in sources},
              'strict': {'status': 'NOT_RUN'}, 'localization': {'status': 'NOT_RUN'},
              'artifacts': [], 'cannot_claim': ['No full G1, model output/token behavior, real sensor or hardware result.',
                                              'Controlled exp replacement is not a corrected Torch oracle or a kernel fix.']}
    try:
        report['checkout_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                                                            stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        report['checkout_commit'] = 'unavailable; use base_commit and actual source hashes'

    def array(name, value):
        path = args.output_dir/(name+'.npy')
        np.save(path, value, allow_pickle=False)
        report['artifacts'].append({'path': path.name, 'bytes': path.stat().st_size, 'sha256': sha(path)})

    exit_code = 2
    try:
        import torch
        from pyignite import PE1d_sincos
        report['torch'] = torch.__version__
        report['torch_cpu_capability'] = torch.backends.cpu.get_cpu_capability()
        torch.set_num_threads(1)
        spec = importlib.util.spec_from_file_location('unchanged_upstream_layers', sources[0])
        upstream = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(upstream)
        with torch.inference_mode():
            reference = upstream.PE1d_sincos(4096, 64).numpy()
            actual = PE1d_sincos(4096, 64)
            report['strict'], mask = comparison(actual, reference)
            exit_code = 0 if report['strict']['status'] == 'PASS' else 1
            array('strict-native', actual); array('strict-original-torch', reference); array('strict-violation-mask', mask)
            exponent = torch.arange(0, 64, 2, dtype=torch.float32) * -(math.log(10000.)/64)
            frequencies = torch.exp(exponent)
            positions = torch.arange(4096, dtype=torch.float32)[:, None]
            phases = positions * frequencies
            array('exponent-torch-fp32', exponent.numpy()); array('frequency-torch-fp32', frequencies.numpy())
            array('phase-torch-fp32', phases.numpy())
            local = {'status': 'LOCALIZATION_ONLY', 'methods': [],
                     'note': 'Reference, tolerance and strict status above are never replaced.'}
            variants = [('numpy-exp-fp32', np.exp(exponent.numpy())),
                        ('double-exp-then-fp32', np.array([math.exp(float(x)) for x in exponent], np.float32)),
                        ('double-multiply-then-exp-fp32', np.array([math.exp(j*(-math.log(10000.)/64)) for j in range(0,64,2)], np.float32))]
            libm_path = ctypes.util.find_library('m')
            if libm_path:
                libm = ctypes.CDLL(libm_path); libm.expf.argtypes = [ctypes.c_float]; libm.expf.restype = ctypes.c_float
                variants.append(('system-libm-expf', np.array([libm.expf(float(x)) for x in exponent], np.float32)))
                local['libm'] = libm_path
            else:
                local['libm'] = 'unavailable; no libm comparison claimed'
            original_freq = frequencies.numpy()
            for name, freq in variants:
                controlled_phase = positions * torch.from_numpy(freq)
                controlled = torch.empty((4096, 1, 64), dtype=torch.float32)
                controlled[:,0,::2] = torch.sin(controlled_phase)
                controlled[:,0,1::2] = torch.cos(controlled_phase)
                array(name+'-frequency', freq); array(name+'-phase', controlled_phase.numpy()); array(name+'-pe', controlled.numpy())
                stats, _ = comparison(actual, controlled.numpy())
                stats['status'] = 'LOCALIZATION_ONLY'  # cannot be mistaken for original strict parity
                stats.update(method=name, frequency_bit_differences=int(np.count_nonzero(freq.view(np.uint32)!=original_freq.view(np.uint32))),
                             max_frequency_ulp=int(np.max(np.abs(freq.view(np.uint32).astype(np.int64)-original_freq.view(np.uint32).astype(np.int64)))),
                             max_phase_delta=float(torch.max(torch.abs(phases-controlled_phase))),
                             frequency_bits=[hex(int(x)) for x in freq.view(np.uint32)])
                local['methods'].append(stats)
            report['localization'] = local
    except (ImportError, OSError, RuntimeError, AttributeError) as exc:
        # If strict already ran, keep that result even when optional localization
        # fails. Otherwise unavailable prerequisites are NOT_RUN, not a pass.
        report['unavailable'] = type(exc).__name__+': '+str(exc)
        report['localization']['error'] = report['unavailable']
    finally:
        encoded = json.dumps(report, indent=2, allow_nan=False)+'\n'
        (args.output_dir/'report.json').write_text(encoded, encoding='utf-8')
        print(encoded)
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
