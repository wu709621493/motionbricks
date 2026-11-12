# PyIgnite 0.2 experimental CPU subset

Independent C++17 FP32 primitives with a Python/NumPy API. No LibTorch, training,
or production-path changes. The distribution is `motionbricks-pyignite`; the
Python import is `pyignite`. This is neither Apache Ignite's client nor PyTorch-Ignite.

See [the engineering report](../../docs/pyignite.md) for build commands, audited
operators, Rust/C++ selection, actual numerical/timing/memory measurements,
limitations and the next migration scope. The [v0.2 review](../../docs/pyignite_v02_zh.md)
contains real G1 **subset** measurements and outstanding numerical limitations.

```sh
# From the repository root, for source development:
python tools/pyignite/build.py
PYTHONPATH=tools/pyignite python -m unittest discover -s tests/pyignite -v

# Build a platform-specific wheel and source distribution:
python -m pip install build
python -m build tools/pyignite --outdir wheelhouse
python -m pip install wheelhouse/*.whl
```

Wheel installation does not run a compiler; source installation does. Linux and
macOS wheels are built natively per architecture. Linux wheels are tagged for
the build platform, **not manylinux-certified** or verified on old glibc versions.
CI artifacts are experimental builds, not a PyPI release.

```python
from pyignite import FCBlock, PositionEmbedding

# Ordered FP32 (weight[out,in], bias[out]) pairs, hidden layers then projection:
model = FCBlock(layers, backend="fused")  # scalar (default), fused, or numpy
y = model(x)

# Preserve a saved model buffer rather than regenerating PE using local libm:
position = PositionEmbedding.from_npy("position.npy", sha256=expected_file_sha256)
z = position(sequence)  # FP32 [batch, time, dimension]
```

The original `PE1d_sincos` generator remains experimental: its historical
PE-4096-64 cross-environment parity gap is **not repaired** by this release.
`PositionEmbedding` consumes an explicit frozen buffer and does not silently
change the generator or its oracle. Training and stochastic dropout are unsupported.

FC backend selection is explicit. `fused` uses one native call and two scratch
buffers reused between hidden layers; scratch is private to each invocation.
Weights have immutable byte ownership and are validated at construction. The
original `scalar` path retains per-call native validation. `numpy` uses the
installed NumPy matrix backend; its speed and rounding depend on that build.
All paths reject non-finite inputs/results and preserve the original FP32 contract.
