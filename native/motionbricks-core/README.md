# MotionBricks Rust core — stage 1

This is an incremental rewrite of the inference operations MotionBricks needs,
not a rewrite of the entire PyTorch framework. It is opt-in and is not wired into
the animation runtime, robot control, ONNX export, or released model loading.

## Language decision

Rust is chosen for explicit ownership, checked indexing and controlled resource
interfaces without a tracing garbage collector. This crate forbids unsafe code
and has no dependencies, including no LibTorch/tch, Python, CUDA or ONNX runtime.
Rust itself does not guarantee lower watts, faster tensor math, hard real-time
execution or physical stability. The scalar reference kernels may be slower than
PyTorch's optimized kernels. No speed or power claim is made.

PyTorch already provides a native C++ API; translating Python calls to that API
would still use PyTorch. Here, codebook lookup and the listed operations execute
as Rust code. Python is retained for test orchestration and the PyTorch oracle.

Sources: [Rust ownership](https://doc.rust-lang.org/book/ch04-00-understanding-ownership.html),
[PyTorch C++ frontend](https://docs.pytorch.org/cppdocs/frontend.html).

## Repository mapping and scope

Inspected source snapshot: `7d78474b0cd0fc9b2c7373df0620f65dcb831a82`.

| Existing source / use | Rust stage 1 | Status |
| --- | --- | --- |
| `tools/onnx/models/quantizer.py`: head-wise gather and overall-index split | `Codebook::decode_heads`, `decode_overall` | Ported for valid inputs |
| `tools/onnx/models/layers.py`: Linear and ReLU building blocks | `Matrix::linear`, `relu` | Primitives only; FCBlock is not ported |
| Softmax for future attention/token selection | `Matrix::softmax` | Primitive only; attention is not ported |
| `tools/onnx/models/vqvae.py` convolutional decoder | None | Pending |
| `tools/onnx/models/g1/model.py` root/pose predictors and checkpoint loading | None | Pending |
| SOMA/G1 preprocessing, full outputs and ONNX export | None | Pending |
| Autograd, training, optimizer, arbitrary tensor views/broadcasting | None | Out of stage 1 scope |

There is no drop-in `torch` namespace, Python binding, automatic backend selection
or model-weight loader. Construct Rust buffers explicitly. Legacy APIs continue
unchanged. No quantum/BEC execution or cross-backend motion parity is claimed.

## Data and numerical contract

Matrices are owned contiguous row-major FP32 with positive dimensions. Linear uses
`[N,I] @ weight[O,I].T + bias[O]`; no implicit casts/broadcasting. Softmax normalizes
rows using max subtraction. Nonfinite inputs and nonfinite outputs are rejected.
FP32 rounding/underflow can still occur. Operations allocate an output buffer and
return Result; these are reference APIs, not allocation-free control-loop APIs.

Codebook storage is `[heads, entries, width]`, indices are `[batch,frames,heads]`
or overall unsigned integers `[batch,frames]`, and output is a Matrix with shape
`[batch*frames, heads*width]`. Lowest head is the least significant base-entries
digit. G1's 8 heads x 10 entries x 32 values require **2,560 stored floats**, not
100 million vectors; the 100 million figure is the combinatorial code space.
Dimensions are explicit; no floating-point root calculation is used.

Intentional stricter behavior: reject an overall index >= code space instead of
upstream modulo wrapping. Negative values cannot enter the unsigned API; the CLI
rejects them. Zero dimensions, overflow, wrong lengths and invalid head indices
are errors. Each numeric buffer is capped at 16,777,216 elements (~64 MiB FP32).
This is not a total process cap: callers can hold many buffers, and owned input
Vec allocations occur before constructor validation. Output allocation is
fallible; no thread, deadline, OS power or physical actuator policy is installed.

## Build and verification

```sh
cd native/motionbricks-core
cargo +1.85.0 test --locked
cargo +1.85.0 build --release --locked
# Repository root, with CPU PyTorch and NumPy installed:
python native/motionbricks-core/tests/parity.py
```

The last command is run from the repository root, not the crate directory.
`parity_probe` is a bounded text test harness, not a production model-serving API.
The Rust crate is dependency-free. CI runs native builds/tests on Ubuntu x86_64,
Ubuntu ARM64 and macOS ARM64. The PyTorch oracle runs on Ubuntu x86_64 only;
cross-platform numerical parity is not established by compilation alone.

Local validation on 2026-11-02: Rust 1.85.0, Python 3.12.14, PyTorch 2.15.0+cpu,
Linux x86_64. Six Rust tests passed; 14 numerical cases and six malformed CLI
requests passed. Actual results are in `tests/parity-results.json` (synthetic
weights, no released checkpoint). Codebook and ReLU require exact FP32 equality;
Linear/Softmax use `abs(error) <= 2e-5 + 1e-5*abs(reference)`. The initial 2e-6
absolute tolerance failed one near-zero linear result by 4.43e-6; this scalar
FP32 implementation accumulates differently from the PyTorch matrix kernel.
The final tolerance is an operator smoke-test criterion, not a model-quality
admission threshold. Maximum observed linear error was 2.29e-5; softmax error
was 2.39e-7. These tests are not a general error bound or performance benchmark.

## Next implementation gates

1. Port Conv1d, normalization, LeakyReLU/SiLU/GELU, positional encodings and
   masked attention with independent operator fixtures, then compose complete
   G1 root/pose/VQ decoder blocks. Test mask and layout semantics explicitly.
2. Add a versioned, strictly validated checkpoint loader preserving parameter
   names, shapes, dtypes and hashes. Compare layer outputs before full motion.
3. Preserve the existing six-input G1 graph contract, valid-frame handling and
   current CPU-reference acceptance gates. Run released-weight parity before
   offering a selectable runtime backend. SOMA requires its own validation.
4. Add a Python/FFI adapter and bounded worker queues. Integrate optional work
   with `sleep_mode`: balance stays independent; discard stale generation on
   sleep/wake; regenerate from measured current state. The current crate does
   not implement those scheduling guarantees.
5. Only after correctness: benchmark watts, wall time, peak memory and wake
   latency, then consider SIMD/BLAS and Metal/CUDA/TPU implementations. GPU
   backends, training and automatic differentiation are separate projects.

The complete PyTorch rewrite requested is therefore not finished by this stage.
This PR establishes a real, tested native implementation and a reviewable path
for replacing the subset needed by this repository.
