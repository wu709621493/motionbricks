"""Run from outside the checkout in a venv containing only the wheel + NumPy."""
import hashlib
import json
from pathlib import Path
import resource
import sys
import tempfile
import time

started = time.perf_counter_ns()
import numpy as np
import pyignite
from pyignite import FCBlock, PE1d_sincos, PositionEmbedding
import_us = (time.perf_counter_ns()-started)/1000

layers = [(np.eye(2, dtype=np.float32), np.zeros(2, np.float32))] * 2
x = np.array([[-2, 3]], np.float32)
for backend in ('scalar', 'fused', 'numpy'):
    np.testing.assert_allclose(FCBlock(layers, backend=backend)(x), [[-.02, 3]])
pe = PE1d_sincos(2, 2)
with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / 'pe.npy'
    np.save(path, pe, allow_pickle=False)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    np.testing.assert_array_equal(PositionEmbedding.from_npy(path, sha256=sha)(
        np.zeros((1, 2, 2), np.float32)), pe.transpose(1, 0, 2))
assert 'torch' not in sys.modules
assert Path(pyignite.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()), 'imported checkout'
print(json.dumps({'status': 'PASS', 'version': pyignite.__version__, 'numpy': np.__version__,
                  'torch_imported': False, 'module': pyignite.__file__,
                  'import_us': import_us,
                  'peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss *
                  (1 if sys.platform == 'darwin' else 1024),
                  'note': 'isolated process after wheel install; tiny smoke workload; import timer excludes interpreter startup'}, indent=2))
