"""Bounded synthetic benchmark; correctness is a gate, timings are observations.

Build the Rust release probes and PyIgnite first. Run from any directory.
Each native timing excludes process startup, fixture construction and serialization.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shlex
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
CRATE = ROOT / 'native/motionbricks-core'
RUST = CRATE / 'target/release/benchmark_probe'
PROBE = CRATE / 'target/release/parity_probe'


def command(args):
    return subprocess.check_output(args, cwd=ROOT, text=True, timeout=120).strip()


def distribution(samples):
    ordered = sorted(samples)
    return {'median_us': statistics.median(samples), 'min_us': min(samples),
            'p95_batch_mean_us': ordered[int(0.95 * (len(ordered)-1))],
            'samples_us': samples}


def timing(fn):
    for _ in range(5):
        fn()
    samples = []
    for _ in range(30):
        start = time.perf_counter_ns()
        for _ in range(20):
            fn()
        samples.append((time.perf_counter_ns() - start) / 20 / 1000)
    return distribution(samples)


def values(n, modulus=31):
    import numpy as np
    return ((np.arange(n) % modulus - modulus // 2) / 32).astype(np.float32)


def run_native(exe, case):
    result = json.loads(command([str(exe), str(case)]))
    return distribution(result['samples_us']), result['values'], result.get('peak_rss_bytes') or None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    import numpy as np
    import torch
    import torch.nn.functional as F
    sys.path.insert(0, str(ROOT / 'tools/pyignite'))
    from pyignite import _native
    spec = importlib.util.spec_from_file_location('review_quantizer', ROOT / 'tools/onnx/models/quantizer.py')
    quantizer = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = quantizer
    spec.loader.exec_module(quantizer)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    build = ROOT / 'build/rust-review'
    build.mkdir(parents=True, exist_ok=True)
    cpp = build / 'pyignite_bench'
    flags = ['-std=c++17', '-O2', '-ffp-contract=off', '-Wall', '-Wextra']
    compile_command = shlex.split(os.environ.get('CXX', 'c++')) + flags + [
        str(ROOT / 'tools/rust_review/pyignite_bench.cpp'),
        str(ROOT / 'tools/pyignite/kernels.cpp'), '-o', str(cpp)]
    command(compile_command)
    cases = []
    with torch.inference_mode():
        for case in range(9):
            rust_timing, rust_values, rust_rss = run_native(RUST, case)
            if case < 6:
                rows = [1, 32, 256][case // 2]
                q = quantizer.QuantizeEMAResetMultiHead(100_000_000, 256, 8)
                weights = torch.from_numpy(values(2560, 257).reshape(8, 10, 32))
                q.vq._codebook.embed.copy_(weights)
                ids = torch.arange(rows).reshape(1, rows) * 7919 % 100_000_000
                heads = torch.stack([(ids // (10 ** h)) % 10 for h in range(8)], dim=-1)
                fn = (lambda: q.dequantize(ids)) if case % 2 == 0 else (lambda: q.vq.get_codes_from_indices(heads))
                name = f'codebook_{"overall" if case % 2 == 0 else "heads"}_{rows}'
                # Independent direct indexing, in addition to the actual upstream oracle.
                reference = np.stack([weights[h, int(heads[0, r, h])].numpy()
                                      for r in range(rows) for h in range(8)]).reshape(rows, 256)
                np.testing.assert_array_equal(fn().numpy().reshape(rows, 256), reference)
                extra = {'shape': [rows, 256], 'pyignite': 'NOT_IMPLEMENTED',
                         'book_bytes': 10240, 'output_bytes': rows * 256 * 4}
            else:
                rows, inputs, outputs = [(1, 32, 32), (32, 128, 64), (32, 256, 256)][case - 6]
                x, w, b = values(rows * inputs).reshape(rows, inputs), values(outputs * inputs).reshape(outputs, inputs), values(outputs)
                tx, tw, tb = map(torch.from_numpy, (x, w, b))
                fn = lambda: F.linear(tx, tw, tb)
                reference = fn().numpy()
                cpp_timing, cpp_values, cpp_rss = run_native(cpp, case)
                np.testing.assert_array_equal(np.array(cpp_values, np.float32).reshape(reference.shape), reference)
                # Same private Linear C ABI as FCBlock, not the full FCBlock API.
                lib = _native()
                def pyignite_linear():
                    y = np.zeros((rows, outputs), dtype=np.float32)
                    if lib.ignite_linear(rows, inputs, outputs, x, w, b, y, 0):
                        raise RuntimeError('PyIgnite rejected fixture')
                    return y
                np.testing.assert_array_equal(pyignite_linear(), reference)
                extra = {'shape': [rows, inputs, outputs], 'pyignite_cpp': cpp_timing,
                         'cpp_peak_rss_bytes': cpp_rss,
                         'pyignite_ctypes': timing(pyignite_linear),
                         'output_bytes': rows * outputs * 4}
                name = f'linear_{rows}_{inputs}_{outputs}'
            actual = np.array(rust_values, np.float32).reshape(reference.shape)
            np.testing.assert_array_equal(actual, reference)
            cases.append({'name': name, 'rust_native': rust_timing, 'torch_python': timing(fn),
                          'rust_peak_rss_bytes': rust_rss,
                          'max_abs_error': float(np.max(np.abs(actual-reference))),
                          'output_sha256': hashlib.sha256(actual.tobytes()).hexdigest(), **extra})
    # Measure process + parse + compute + serialize separately; never divide into kernel time.
    cold = []
    for _ in range(30):
        start = time.perf_counter_ns()
        p = subprocess.run([str(PROBE)], input='relu 1 1 1 1', capture_output=True,
                           text=True, check=True, timeout=10)
        assert float(p.stdout) == 1.0
        cold.append((time.perf_counter_ns()-start)/1000)
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in [CRATE / 'src/lib.rs', CRATE / 'src/bin/benchmark_probe.rs',
                        ROOT / 'tools/rust_review/pyignite_bench.cpp', Path(__file__),
                        ROOT / 'tools/pyignite/kernels.cpp', ROOT / 'tools/onnx/models/quantizer.py']}
    report = {
        'status': 'PASS', 'fixture': 'deterministic dyadic FP32; synthetic weights; no checkpoint',
        'platform': platform.platform(), 'machine': platform.machine(), 'python': platform.python_version(),
        'numpy': np.__version__, 'torch': torch.__version__, 'torch_threads': torch.get_num_threads(),
        'rustc': command(['rustc', '--version']), 'compiler': command(['c++', '--version']).splitlines()[0],
        'cpp_flags': flags, 'rust_profile': 'Cargo release, opt-level=3; no target-cpu=native/fast-math',
        'rustflags': os.environ.get('RUSTFLAGS', ''),
        'git_head': command(['git', 'rev-parse', 'HEAD']),
        'git_dirty': bool(command(['git', 'status', '--porcelain'])), 'source_sha256': hashes,
        'cpu': next((s.split(':', 1)[1].strip() for s in Path('/proc/cpuinfo').read_text().splitlines()
                     if s.startswith('model name')), 'unknown') if sys.platform == 'linux' else platform.processor(),
        'affinity': sorted(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None,
        'method': {'warmup_calls': 5, 'samples': 30, 'calls_per_sample': 20,
                   'p95_note': 'p95 of batch means, NOT single-request tail latency',
                   'order': 'fixed case/backend order; uncontrolled frequency and shared host'},
        'boundary_note': 'Rust: owned output, input validated at construction, result finite scan. C++: unchanged C ABI rescans input/weights each call; harness allocates output. Torch: Python dispatch and allocation. ctypes: Python/FFI + same kernel. These are API costs, not a language ranking.',
        'cases': cases, 'cli_process_roundtrip': distribution(cold),
        'rss_note': 'Linux /proc/self/status VmHWM inside each fresh native process after timing; whole process including fixtures/runtime, not per-call allocations. null elsewhere.',
        'binary_bytes': {'rust_benchmark_unstripped': RUST.stat().st_size,
                         'rust_parity_unstripped': PROBE.stat().st_size, 'cpp_benchmark_unstripped': cpp.stat().st_size},
    }
    report['cli_process_roundtrip']['p95_process_us'] = report['cli_process_roundtrip'].pop('p95_batch_mean_us')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f'PASS: {len(cases)} cases; {args.output}')


if __name__ == '__main__':
    main()
