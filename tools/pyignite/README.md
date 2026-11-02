# PyIgnite 0.1 prototype

Independent C++17 FP32 PE1d_sincos and eval-only FCBlock with a Python/NumPy API.
No LibTorch, no training, no production-path changes. This is not PyTorch-Ignite.

See [the engineering report](../../docs/pyignite.md) for build commands, audited
operators, Rust/C++ selection, actual numerical/timing/memory measurements,
limitations and the next migration scope. Build with `python tools/pyignite/build.py`
from the repository root before adding `tools/pyignite` to PYTHONPATH.
