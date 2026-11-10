"""Compare Rust kernels against actual PyTorch and the repository quantizer.

PyTorch is an oracle only; the Rust executable never links it.
Run from any directory after cargo build --release.
"""
import importlib.util
import json
import platform
from pathlib import Path
import subprocess
import sys

import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[3]
CRATE = ROOT / 'native' / 'motionbricks-core'
EXE = CRATE / 'target' / 'release' / 'parity_probe'
SPEC = importlib.util.spec_from_file_location('mb_quantizer_oracle', ROOT / 'tools/onnx/models/quantizer.py')
quantizer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = quantizer
SPEC.loader.exec_module(quantizer)
torch.set_num_threads(1)
torch.manual_seed(7096)
results = []


def run(op, dims, parts, expected, *, exact=False):
    words = [op, *map(str, dims)]
    for part in parts:
        values = part.reshape(-1).tolist() if isinstance(part, torch.Tensor) else part
        words.extend(map(str, values))
    process = subprocess.run([str(EXE)], input=' '.join(words), text=True,
                             capture_output=True, check=True, timeout=10)
    actual = torch.tensor([float(x) for x in process.stdout.split()], dtype=torch.float32)
    expected = expected.detach().reshape(-1).float()
    if actual.numel() != expected.numel():
        raise AssertionError('output length mismatch')
    torch.testing.assert_close(actual, expected, rtol=0 if exact else 1e-5,
                               atol=0 if exact else 2e-5)
    results.append({'operation': op, 'dimensions': list(dims),
                    'max_abs_error': (actual-expected).abs().max().item()})


for rows, inputs, outputs in [(1,1,1), (3,7,5), (8,32,17), (4,256,128)]:
    x, w, b = torch.randn(rows,inputs), torch.randn(outputs,inputs), torch.randn(outputs)
    run('linear', (rows,inputs,outputs), [x,w,b], F.linear(x,w,b))
for rows, width in [(1,1), (4,7), (16,256)]:
    x = torch.randn(rows,width)*20
    run('softmax', (rows,width,1), [x], F.softmax(x,dim=-1))
    run('relu', (rows,width,1), [x], F.relu(x), exact=True)
x = torch.tensor([[10000.,10000.,10000.],[-10000.,0.,10000.]])
run('softmax', (2,3,1), [x], F.softmax(x,dim=-1))
for heads, entries, width, batch, frames in [(1,3,5,2,7), (2,4,3,3,5), (8,10,32,2,16)]:
    q = quantizer.QuantizeEMAResetMultiHead(entries**heads, heads*width, heads)
    weights = torch.randn(heads,entries,width)
    q.vq._codebook.embed.copy_(weights)
    ids = torch.randint(entries**heads,(batch,frames),dtype=torch.int64)
    ids[0,0] = 0
    ids[-1,-1] = entries**heads-1
    run('codebook', (heads,entries,width), [weights,[batch,frames],ids],
        q.dequantize(ids), exact=True)

# Failures must be explicit, not coerced or wrapped.
for bad in ['unknown 1 1 1', 'relu 0 1 1', 'relu 1 1 1 nan',
            'relu 1 1 1 0 trailing', 'codebook 1 2 1 0 1 1 1 2',
            'codebook 1 2 1 0 1 1 1 -1']:
    p = subprocess.run([str(EXE)], input=bad, text=True, capture_output=True, timeout=10)
    if p.returncode != 2 or p.stdout:
        raise AssertionError(f'invalid request not rejected: {bad}')
print(json.dumps({'status': 'PASS', 'python': platform.python_version(),
                  'torch': torch.__version__, 'platform': platform.platform(),
                  'cases': results, 'invalid_requests_rejected': 6}, indent=2))
