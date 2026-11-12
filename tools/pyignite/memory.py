"""Isolated process high-water RSS (includes runtime imports), not allocator profiling."""
import argparse
import json
import platform
import resource
import sys
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument('backend', choices=['native','fused','numpy','torch'])
args = parser.parse_args()
def rss():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024)
before = rss()
if args.backend != 'torch':
    from pyignite import FCBlock
else:
    import torch
    torch.set_num_threads(1)
after_import = rss()
rng = np.random.default_rng(20261102)
layers = [(rng.normal(0,.1,(o,i)).astype(np.float32),np.zeros(o,np.float32))
          for i,o in [(128,256),(256,256),(256,64)]]
x = rng.normal(size=(32,128)).astype(np.float32)
if args.backend != 'torch':
    model = FCBlock(layers, backend='scalar' if args.backend == 'native' else args.backend)
    for _ in range(100): y = model(x)
else:
    modules = []
    for index,(w,b) in enumerate(layers):
        layer = torch.nn.Linear(w.shape[1],w.shape[0])
        with torch.no_grad():
            layer.weight.copy_(torch.from_numpy(w)); layer.bias.copy_(torch.from_numpy(b))
        modules.append(layer)
        if index < len(layers)-1: modules.append(torch.nn.LeakyReLU(inplace=True))
    model = torch.nn.Sequential(*modules).eval()
    with torch.inference_mode():
        tx = torch.from_numpy(x)
        for _ in range(100): y = model(tx)
after_run = rss()
print(json.dumps({'backend':args.backend, 'platform':platform.platform(),
    'numpy_process_peak_bytes':before,'after_backend_import_peak_bytes':after_import,
    'after_100_calls_peak_bytes':after_run,'peak_growth_after_import_bytes':after_run-after_import,
    'note':'Fresh process; peak growth is not live allocation or per-call peak. Synthetic source arrays retained in both processes.'},indent=2))
