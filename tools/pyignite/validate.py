"""Compare the actual upstream layers.py against native kernels; emit JSON."""
import argparse
import importlib.util
import json
import platform
import resource
import statistics
import subprocess
import sys
import time
from pathlib import Path
import numpy as np
import torch
from pyignite import FCBlock, PE1d_sincos

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('upstream_layers', ROOT / 'tools/onnx/models/layers.py')
upstream = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upstream)
torch.set_num_threads(1)
SEED = 20261102

def fixture(depth, width, size_in, size_out, shape, dropout=0.0):
    torch.manual_seed(SEED)
    model = upstream.FCBlock(depth, width, size_in, size_out, dropout).eval()
    rng = np.random.default_rng(SEED)
    with torch.no_grad():
        for p in model.parameters():
            p.copy_(torch.from_numpy(rng.normal(0, 0.1, p.shape).astype(np.float32)))
    layers = [m for m in model.fc_layers if isinstance(m, torch.nn.Linear)] + [model.forward_projection]
    native = FCBlock([(m.weight.detach().numpy(), m.bias.detach().numpy()) for m in layers])
    x = rng.normal(size=shape).astype(np.float32)
    return model, native, x

def timing(fn):
    for _ in range(5): fn()
    times = []
    for _ in range(30):
        start = time.perf_counter_ns()
        fn()
        times.append((time.perf_counter_ns()-start)/1000)
    return {'median_us': statistics.median(times), 'min_us': min(times), 'repeats': 30}

def compare(name, native_fn, torch_fn, extra):
    with torch.inference_mode():
        reference = torch_fn().numpy()
        actual = native_fn()
        np.testing.assert_allclose(actual, reference, atol=2e-5, rtol=2e-5)
        for _ in range(10):
            np.testing.assert_array_equal(native_fn(), actual)
        delta = np.abs(actual.astype(np.float64)-reference)
        return {'name': name, 'shape': list(actual.shape), 'max_abs_error': float(delta.max()),
            'max_relative_error_floor_1e-6': float((delta / np.maximum(np.abs(reference), 1e-6)).max()),
            'native': timing(native_fn), 'torch': timing(torch_fn),
            'output_bytes': actual.nbytes, **extra}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    results = []
    for n, d in [(1,2), (17,32), (256,512), (4096,64)]:
        results.append(compare(f'PE-{n}-{d}', lambda: PE1d_sincos(n,d),
            lambda: upstream.PE1d_sincos(n,d), {'native_extra_kernel_heap_bytes': 0}))
    for depth, width, si, so, shape, dropout in [
        (1,8,3,2,(3,),0), (2,32,7,5,(4,7),0.3),
        (3,64,16,9,(2,11,16),0), (2,256,128,64,(32,128),0)]:
        model, native, x = fixture(depth,width,si,so,shape,dropout)
        tx = torch.from_numpy(x)
        results.append(compare(f'FC-{depth}-{width}-{shape}', lambda: native(x), lambda: model(tx),
            {'weights_bytes_per_implementation': native.weight_bytes, 'input_bytes': x.nbytes,
             'native_max_two_layer_output_buffers_bytes':
                int(np.prod(shape[:-1])) * max(2*width,width+so)*4, 'eval_dropout': dropout}))
    report = {'seed': SEED, 'platform': platform.platform(), 'machine': platform.machine(),
        'python': platform.python_version(), 'numpy': np.__version__, 'torch': torch.__version__,
        'compiler': subprocess.check_output(['c++','--version'],text=True).splitlines()[0],
        'threads': 1, 'atol': 2e-5, 'rtol': 2e-5,
        'source_sha': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'memory_note': 'Buffer accounting excludes allocator/NumPy overhead. RSS is entire validation process including both runtimes, not isolated kernel memory.',
        'combined_process_peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024),
        'results': results}
    encoded = json.dumps(report, indent=2) + '\n'
    if args.output: args.output.write_text(encoded)
    print(encoded)

if __name__ == '__main__': main()
