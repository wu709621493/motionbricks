"""Reproducible v0.2 subset parity and single-request latency measurements.

No checkpoint is downloaded implicitly. --g1-root must identify the released file.
Run legacy strict PE audit separately: this program does not fix its known gap.
"""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import tempfile
import time

import numpy as np
import onnx
from onnx import helper, numpy_helper, TensorProto
import onnxruntime as ort
import torch

from pyignite import FCBlock, PositionEmbedding
from g1_subset import load_g1_root_subset

ROOT = Path(__file__).resolve().parents[2]
ATOL = RTOL = 2e-5
SEED = 20261112
spec = importlib.util.spec_from_file_location('original_layers', ROOT / 'tools/onnx/models/layers.py')
upstream = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upstream)


def digest(array):
    return hashlib.sha256(array.tobytes()).hexdigest()


def error(actual, reference):
    delta = np.abs(actual.astype(np.float64) - reference.astype(np.float64))
    violations = int(np.count_nonzero(delta > ATOL + RTOL * np.abs(reference.astype(np.float64))))
    return {'status': 'PASS' if not violations and np.isfinite(actual).all() else 'FAIL',
            'max_abs_error': float(delta.max()), 'violations': violations,
            'output_sha256': digest(actual), 'reference_sha256': digest(reference)}


def make_torch(layers):
    # Both synthetic and real subsets have uniform hidden width, matching the
    # unmodified upstream FCBlock constructor. Load its exact named parameters.
    model = upstream.FCBlock(len(layers)-1, layers[0][0].shape[0],
                             layers[0][0].shape[1], layers[-1][0].shape[0]).eval()
    modules = list(model.fc_layers) + [model.forward_projection]
    with torch.no_grad():
        for module, (w, b) in zip(modules, layers):
            module.weight.copy_(torch.from_numpy(w))
            module.bias.copy_(torch.from_numpy(b))
    return model


def make_ort(layers, shape):
    nodes, initializers, outputs = [], [], []
    previous = 'x'
    for i, (w, b) in enumerate(layers):
        initializers.extend([numpy_helper.from_array(w.T.copy(), f'w{i}'),
                             numpy_helper.from_array(b, f'b{i}')])
        nodes.extend([helper.make_node('MatMul', [previous, f'w{i}'], [f'm{i}']),
                      helper.make_node('Add', [f'm{i}', f'b{i}'], [f'a{i}'])])
        previous = f'a{i}'
        if i < len(layers)-1:
            nodes.append(helper.make_node('LeakyRelu', [previous], [f'h{i}'], alpha=.01))
            previous = f'h{i}'
        outputs.append(helper.make_tensor_value_info(previous, TensorProto.FLOAT,
                                                     [*shape[:-1], w.shape[0]]))
    graph = helper.make_graph(nodes, 'verified-fc-subset',
                              [helper.make_tensor_value_info('x', TensorProto.FLOAT, shape)],
                              outputs, initializers)
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid('', 17)], ir_version=9)
    onnx.checker.check_model(model)
    options = ort.SessionOptions()
    options.intra_op_num_threads = options.inter_op_num_threads = 1
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    # Do not let idle ORT workers spin while measuring the other backends.
    options.add_session_config_entry('session.intra_op.allow_spinning', '0')
    return ort.InferenceSession(model.SerializeToString(), options, providers=['CPUExecutionProvider'])


def fc_case(name, layers, shape, rng, samples):
    x = rng.normal(size=shape).astype(np.float32)
    model = make_torch(layers)
    tx = torch.from_numpy(x)
    reference = model(tx).numpy()
    session = make_ort(layers, list(shape))
    ort_outputs = session.run(None, {'x': x})
    intermediate = []
    h = tx
    for layer, relu in zip(model.fc_layers, model.relu_layers):
        h = relu(layer(h))
        intermediate.append(h.numpy().copy())
    intermediate.append(reference)
    traces = [error(a, b) for a, b in zip(ort_outputs, intermediate)]
    backends, construction = {}, {}
    for backend in ('scalar', 'fused', 'numpy'):
        start = time.perf_counter_ns()
        backends[backend] = FCBlock(layers, backend=backend)
        construction[backend] = (time.perf_counter_ns()-start)/1000
    calls = {key: (lambda obj=obj: obj(x)) for key, obj in backends.items()}
    calls['torch'] = lambda: model(tx)
    calls['ort'] = lambda: session.run([session.get_outputs()[-1].name], {'x': x})[0]
    checks, first, timings = {}, {}, {key: [] for key in calls}
    for key, fn in calls.items():
        start = time.perf_counter_ns()
        output = fn()
        first[key] = (time.perf_counter_ns()-start)/1000
        actual = output.numpy() if key == 'torch' else output
        checks[key] = error(actual, reference)
        checks[key]['repeat_identical'] = all(np.array_equal(
            (fn().numpy() if key == 'torch' else fn()), actual) for _ in range(3))
        for _ in range(5):
            fn()
    order_rng = np.random.default_rng(SEED)
    for _ in range(samples):
        for key in order_rng.permutation(list(calls)):
            start = time.perf_counter_ns()
            calls[key]()
            timings[key].append((time.perf_counter_ns()-start)/1000)
    return {'name': name, 'input_shape': list(shape), 'input_sha256': digest(x),
            'weight_shapes': [list(w.shape) for w, _ in layers],
            'weight_sha256': [{'w': digest(w), 'b': digest(b)} for w, b in layers],
            'checks': checks, 'ort_intermediate_vs_torch': traces,
            'construction_us': construction,
            'timing': {key: {'first_call_us': first[key], 'median_us': statistics.median(values),
                             'p95_single_request_us': float(np.percentile(values, 95)),
                             'samples_us': values} for key, values in timings.items()}}


def position_case(name, buffer, shape, rng):
    original = upstream.PositionEmbedding(buffer.shape[0], buffer.shape[2]).eval()
    with torch.no_grad():
        original.embed.copy_(torch.from_numpy(buffer))
    x = rng.normal(size=shape).astype(np.float32)
    reference = original(torch.from_numpy(x)).numpy()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'position.npy'
        np.save(path, buffer, allow_pickle=False)
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        actual = PositionEmbedding.from_npy(path, sha256=sha)(x)
    return {'name': name, 'buffer_shape': list(buffer.shape), 'input_shape': list(shape),
            'buffer_sha256': digest(buffer), 'npy_sha256': sha,
            'bitwise_equal': bool(np.array_equal(actual, reference)), **error(actual, reference)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--g1-root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--samples', type=int, default=50)
    args = parser.parse_args()
    if args.samples < 20:
        parser.error('--samples must be at least 20')
    torch.set_num_threads(1)
    rng = np.random.default_rng(SEED)
    cases, positions = [], []
    with torch.inference_mode():
        for dims, shape in [([3, 8, 2], (3,)), ([7, 32, 32, 5], (4, 7)),
                            ([128, 256, 256, 64], (32, 128))]:
            layers = [(rng.normal(0, .1, (o, i)).astype(np.float32),
                       rng.normal(0, .1, o).astype(np.float32)) for i, o in zip(dims, dims[1:])]
            cases.append(fc_case(f'synthetic-{shape}', layers, shape, rng, args.samples))
        for n, d in [(17, 32), (4096, 64)]:
            buffer = upstream.PE1d_sincos(n, d).numpy()
            positions.append(position_case(f'frozen-PE-{n}-{d}', buffer, (2, n, d), rng))
        checkpoint = {'status': 'NOT_RUN', 'reason': '--g1-root not supplied'}
        if args.g1_root:
            layers, pe, metadata = load_g1_root_subset(args.g1_root)
            checkpoint = {'status': 'EXECUTED_SUBSET', **metadata}
            for shape in [(1, 384), (2, 4, 384)]:
                cases.append(fc_case(f'g1-root-start-{shape}', layers, shape, rng, args.samples))
            positions.append(position_case('g1-root-saved-position', pe, (2, 16, 512), rng))
    passed = all(c['status'] == 'PASS' and c['repeat_identical'] for case in cases for c in case['checks'].values())
    passed &= all(c['status'] == 'PASS' for case in cases for c in case['ort_intermediate_vs_torch'])
    passed &= all(p['status'] == 'PASS' and p['bitwise_equal'] for p in positions)
    sources = ['tools/pyignite/kernels.cpp', 'tools/pyignite/pyignite/__init__.py',
               'tools/pyignite/pyignite/position.py', 'tools/pyignite/g1_subset.py',
               'tools/pyignite/review.py', 'tools/onnx/models/layers.py', 'tools/onnx/checksums.py']
    blas_info = io.StringIO()
    import contextlib
    with contextlib.redirect_stdout(blas_info):
        np.show_config()
    report = {'status': 'PASS' if passed else 'FAIL', 'scope': 'FC subsets and saved position buffers only',
              'dynamic_pe_known_gap': 'Not fixed; run unchanged strict audit separately',
              'seed': SEED, 'atol': ATOL, 'rtol': RTOL, 'python': platform.python_version(),
              'numpy': np.__version__, 'torch': torch.__version__, 'onnx': onnx.__version__,
              'onnxruntime': ort.__version__, 'platform': platform.platform(),
              'compiler': subprocess.check_output(['c++', '--version'], text=True).splitlines()[0],
              'cpp_flags': ['-std=c++17', '-O2', '-ffp-contract=off', '-fPIC'],
              'torch_cpu_capability': torch.backends.cpu.get_cpu_capability(),
              'numpy_config': blas_info.getvalue(),
              'thread_environment': {k: os.getenv(k) for k in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'ATEN_CPU_CAPABILITY')},
              'git_base_or_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'source_sha256': {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources},
              'method': '5 warmups; randomized backend order; individual request times; prebuilt weights/sessions; no speed threshold',
              'limits': 'Shared host, no locked CPU frequency; input conversion excluded for Torch; first call is not process cold start; no full model/robot/energy result',
              'checkpoint': checkpoint, 'fc_cases': cases, 'position_cases': positions}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f"{report['status']}: {len(cases)} FC cases, {len(positions)} position cases; {args.output}")
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
