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

## Legacy CPU compatibility experiments

See the [Chinese compatibility and fault-handling report](../../docs/pyignite_legacy_cpu_zh.md)
for Pentium, AMD K5/K6/Athlon, Cyrix and VIA candidate tiers, dependency boundaries,
and the distinction between software errors and physical aging. No physical
Pentium-era machine or complete legacy Python environment is certified here.

```sh
# Native smoke runs without Python/NumPy on the target; this wrapper is optional:
python tools/pyignite/build.py --kind smoke
python -S tools/pyignite/doctor.py --binary tools/pyignite/build/host/pyignite-smoke

# Linux GCC 13+ with 32-bit development libraries; separate outputs:
python tools/pyignite/build.py --profile p5-x87 --kind smoke
python tools/pyignite/build.py --profile ia32-sse2 --kind smoke
```

`p5-x87` requests an i586/x87 baseline; `ia32-sse2` requires SSE2. These switches
do not rebuild the loader, libc, Python, NumPy or BLAS. A successful build or a
32-bit run on a modern host is not a Pentium compatibility result. The x87
profile needs separate numerical qualification; full FP32 parity is unverified.
The standalone executable covers only tiny known answers, nonfinite/overflow
rejection, PE at the origin, and one division residual; it cannot diagnose cache
wear or certify dynamic PE. `doctor.py` contains a timeout/crash within its probe
child. It is an opt-in check, not a supervisor for ordinary in-process FC calls.
Its event inputs are caller-supplied; it does not read MCE/EDAC or temperature.

For small working sets on a functioning machine:

```python
model = FCBlock(layers, backend="scalar", max_batch_rows=8)
y = model(x)
```

This bounds hidden activation rows; weights, a possible contiguous input copy,
and the full output still consume memory. It neither bypasses cache nor repairs
hardware. Choose the chunk size from measurements; NumPy/BLAS chunking can change
rounding. A late chunk failure raises without returning a partial output.

