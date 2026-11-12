# PyIgnite: independent PyTorch dependency migration prototype

2026-11-12: [v0.2 implementation and evidence](pyignite_v02_zh.md) adds a frozen
position-buffer path, explicit fused/NumPy FC backends, checksum-verified real G1
subgraph validation, and platform wheel builds. The historical dynamic-PE gap
remains open. Measurements below describe v0.1 and are retained unchanged.

Status: experimental CPU FP32 inference library, 2026-11-02. Audited MotionBricks
base `f19dd01432b2eadf3800b3c71f99a092c741aa8a`. PyIgnite is a local project name,
not PyTorch-Ignite and not a published package. No production imports, exporter
changes, checkpoint conversions or robot execution are introduced.

2026-11-10: the [independent Rust integration review](rust_integration_review_zh.md)
adds a shared Linear microbenchmark and preserves Rust's distinct codebook experiment.
The [current benchmark report](rust_benchmark_20261110_zh.md) also records a failed
large-PE parity case on the review host; historical passing numbers below have not
been replaced or generalized to the new environment. Kernels and tolerances are unchanged.
The [PR #66 readiness review](rust_pr66_readiness_zh.md) retains that strict failure
and gates the unrelated Rust integration on a freshly built, pinned-main regression
comparison. A passing regression check is not a claim that all PE parity cases pass.

## Decision: C++17 kernels with a Python/NumPy boundary

| Consideration | C++17 route (selected) | Rust route |
|---|---|---|
| Linux x86-64 | Native GCC/Clang shared library; tested here with GCC 13.3 | Native Rust toolchain target; feasible, not implemented |
| Linux ARM64 | Same portable scalar source; native GCC/Clang build planned in CI | `aarch64-unknown-linux-gnu` target and host tools |
| macOS ARM64 | Apple Clang, `.dylib`; native CI planned | `aarch64-apple-darwin` target and host tools |
| Build dependencies | C++ compiler, Python and NumPy; no CMake, BLAS, CUDA or LibTorch | Cargo/rustc plus Python binding or C ABI; no LibTorch needed if kernels are independent |
| Maintenance | Small direct C ABI; buffer lifetime and sizes need explicit validation | Safe slices and ownership improve internal memory safety; FFI still needs validation |
| Runtime compatibility | No C++ objects cross ABI; build separately for each OS/architecture; libstdc++/libc++ and libc remain system dependencies | Native artifacts also built per target; Python/C boundary still needed |
| ORT integration | Official C and C++ APIs make a later native integration direct | Requires C FFI or a separately maintained Rust wrapper |

This is a project-specific simplicity decision, not a performance or general language
ranking. No Rust benchmark was performed. Rust remains worth revisiting if the scope
expands into a larger tensor engine. Current C++ scalar loops prioritize an inspectable
reference implementation, not optimized GEMM. No architecture-specific SIMD flags or
`fast-math` are used; FP contraction is disabled. Architecture support is a build
hypothesis until native tests complete; it is not a claim about a specific Apple chip.

Primary references consulted:
- [Rust target/platform support](https://doc.rust-lang.org/rustc/platform-support.html)
- [ONNX Runtime C++ API and C wrapper relationship](https://onnxruntime.ai/docs/get-started/with-cpp)
- [ONNX Runtime C/C++ API](https://onnxruntime.ai/docs/api/c/c_cpp_api.html)

## Actual exporter audit

`tools/onnx/pyproject.toml` pins Python 3.12, NumPy 1.26.4,
`torch==2.14.0+cpu`, ONNX 1.23.2 and safetensors 0.8.0. The root runtime does not
list Torch; the main inference path is TensorRT. `export.py` uses
`torch.onnx.export` at opset 17, validates the environment, loads checkpoint-backed
models and validates staged ONNX output. That baseline stays intact.

The generated [call inventory](results/pyignite_operator_audit.json) includes source
paths and line numbers. Regenerate with `python tools/pyignite/audit.py`. It enumerates
static Torch-qualified calls including constructors/utilities, not a complete traced
ATen graph. Tensor methods, overloaded arithmetic and checkpoint-dependent branches
must also be reviewed. The manual structural audit is:

| Source area | Structure and operators | Migration implication |
|---|---|---|
| `models/layers.py` | FCBlock, fixed sin/cos PE, PositionEmbedding; Linear, LeakyReLU, Dropout, parameter storage, broadcast/permute | First-phase eval-only subset implemented |
| Same shared layers | Conv1d, residual addition, dilation/padding/stride, ReLU/SiLU/GELU, LayerNorm/GroupNorm/BatchNorm1d, nearest upsampling, token masks | Separate convolution/normalization semantics and boundary tests needed |
| `models/g1/networks.py`, `models/soma/networks.py` | Root and pose networks; TransformerEncoder/TransformerEncoderLayer, embedding tables, MLP projections, masks, token logits | Attention, normalization, position handling and masking remain Torch-dependent |
| `models/*/inference.py` | Iterative token prediction/remasking, random samples, argmax, gather/scatter, sorting, softmax, one-hot, where, clipping, concatenation and broadcasting | RNG and discrete decisions require intermediate-output comparison, not just final allclose |
| `models/*/model.py`, `g1/rig.py`, shared motion/rotation helpers | Batched wrappers, predictor wiring, pose preprocessing/postprocessing, quaternion/rotation math, norms, trig, matrix products and cumulative operations | Model-space conventions and numerical stability are separate contracts |
| `checkpoints.py`, `export.py` | Checkpoint materialization, state loading, eval/inference context and ONNX serialization | Kernel parity does not replace loading, tracing or graph validation |

FCBlock is imported as `mlp` in both G1 and SOMA networks. PositionEmbedding adds
the PE buffer to transposed/broadcast inputs and applies dropout. Some model parameters
and configuration sizes come from checkpoints; static inspection cannot establish
which optional branch executes for every checkpoint. Training-related constructor
options in source are not evidence of an executed training path in this exporter.

## Implemented contract

`tools/pyignite/pyignite` imports NumPy and ctypes, never Torch. Building is explicit;
import does not invoke a compiler or download dependencies. The private C ABI requires
valid non-overlapping buffers; the Python boundary owns allocation and validates
shape/dtype before calling it. Direct raw-pointer use is not a public safe API.

- `PE1d_sincos(sequence, dimension)` returns contiguous FP32 `[sequence, 1, dimension]`,
  matching the **actual upstream return shape**, despite its shorter docstring.
  For even `j`, frequency is `exp(j * -log(10000)/dimension)`; even/odd channels
  are sine/cosine of position times frequency.
- `FCBlock([(W0,b0), ..., (Wout,bout)])(x)` accepts FP32 `[..., input_width]`.
  Weights are `[out,in]`; forward is `x @ W.T + b`. Every hidden layer uses
  LeakyReLU slope 0.01; final projection has no activation. Positive leading
  dimensions, including rank-one inputs, are supported. Input strides are copied
  when needed. Weights are copied once to owned arrays.
- Ordered weight pairs are an explicit constructor adapter, **not** a drop-in
  `torch.nn.Module` or state_dict API. The validator extracts actual upstream
  Linear modules in order, including correct placement around eval-mode Dropout.
- Evaluation only: upstream dropout is identity in `.eval()`, including nonzero
  configured dropout. Training, backward, optimizers, GPU and other dtypes are absent.
- Zero/negative/odd PE dimensions, empty tensors, malformed/disconnected weights,
  wrong dtypes and non-finite input/weights/biases are rejected. FC accumulation
  overflow is rejected. These are intentionally stricter error contracts than Torch.
  `num_layers=0` and zero-size tensors are outside the supported subset.

## Reproduce from the repository root

Use an isolated environment; do not install the full MotionBricks application:

```sh
python3.12 -m venv .venv-pyignite
. .venv-pyignite/bin/activate
python -m pip install -r tools/pyignite/requirements.txt
python tools/pyignite/build.py
python -m unittest discover -s tests/pyignite -v
python -m pip install -r tools/pyignite/requirements-validation.txt
python tools/pyignite/validate.py --output /tmp/pyignite-parity.json
python tools/pyignite/memory.py native
python tools/pyignite/memory.py torch
```

For a caller, add `tools/pyignite` to PYTHONPATH and `from pyignite import FCBlock,
PE1d_sincos`. The local source package is deliberately not registered on PyPI.
Set `CXX` to choose a compiler. The workflow `pyignite.yml` builds/tests natively on
Ubuntu x86-64, Ubuntu ARM64 and macOS ARM64, with dependency-install failures treated
as failures, never successful parity skips. Each job uploads its own measurements.

## Validation and measurement limitations

The checked-in run used Linux x86-64, Python 3.12.14, GCC 13.3.0, NumPy 2.3.5 and
**Torch 2.15.0+cpu**, not the exporter's pinned 2.14.0+cpu/NumPy 1.26.4 environment.
It directly imports unmodified `tools/onnx/models/layers.py` as the oracle. This is
source-level parity against that installed Torch build; exact exporter-environment
parity remains a separate gate. requirements-validation pins the observed version
(public release version permits the CPU local version suffix). Package-wheel
availability on other platforms is not assumed from this local run.

Seed 20261102 controls synthetic normal weights and inputs. Four PE shapes and four
FC configurations cover depth, width, rank 1/2/3 inputs and eval dropout 0.3. Elementwise
acceptance is `abs(actual-reference) <= 2e-5 + 2e-5*abs(reference)`. Relative error is
reported as `abs(error)/max(abs(reference),1e-6)`; it is not a standalone acceptance
test. Near-zero trigonometric outputs explain relatively large relative errors.
FP32 summation order and platform libm implementations can differ; passing here does
not prove arbitrary shapes pass. Repeated native outputs must be bitwise identical
within one process (10 repetitions per parity case; 100 calls in contract tests).

Timing uses 5 warmups and 30 measured calls, median and minimum microseconds, one
Torch thread, inference mode and prebuilt weights. Native timing includes Python/FFI,
validation, allocations and computation; Torch timing excludes tensor conversion.
These are host-specific end-to-end primitive timings, not isolated kernel benchmarks.
CPU frequency and host scheduling were not controlled. Large FC loops are substantially
slower than Torch's optimized linear kernels; do not infer a speedup from dependency
reduction. See [raw parity results](results/pyignite_v1.json).

| Case | Max absolute error | Max relative error (floor 1e-6) | Native median µs | Torch median µs |
|---|---:|---:|---:|---:|
| PE-1-2 | 0 | 0 | 3.62 | 19.70 |
| PE-17-32 | 5.96046e-08 | 1.10317e-07 | 4.97 | 20.96 |
| PE-256-512 | 7.62194e-06 | 0.0102372 | 808.18 | 358.83 |
| PE-4096-64 | 1.52588e-05 | 0.0102372 | 1072.87 | 644.37 |
| FC-1-8-(3,) | 1.49012e-08 | 8.95723e-08 | 27.31 | 13.48 |
| FC-2-32-(4, 7) | 2.98023e-08 | 1.29555e-05 | 61.64 | 23.86 |
| FC-3-64-(2, 11, 16) | 1.24797e-07 | 4.47464e-05 | 233.91 | 35.18 |
| FC-2-256-(32, 128) | 2.74181e-06 | 0.00089893 | 4350.50 | 84.18 |

Seven contract tests pass locally: known values/shapes, invalid dimensions, dtype and
training refusal, NaN/Inf, arithmetic overflow, repeated/noncontiguous inputs with
weight-copy isolation, and a fresh process proving Torch-independent import/execution.

### Memory

Fresh-process `memory.py` results for the 2-hidden-layer, width-256 FC fixture:

| Backend | Peak RSS after import | Peak RSS after 100 calls | Increase in high-water RSS |
|---|---:|---:|---:|
| PyIgnite | 21,757,952 B | 25,964,544 B | 4,206,592 B |
| Torch | 224,841,728 B | 233,574,400 B | 8,732,672 B |

These are whole-process high-water RSS observations, including Python, NumPy,
backend loading, fixture generation and retained synthetic arrays. They are **not**
per-call allocations, isolated kernel memory, or proof of leak freedom. Separate
process imports dominate this comparison. Raw [native](results/pyignite_memory_native.json)
and [Torch](results/pyignite_memory_torch.json) reports preserve the measurements.

For that fixture, owned native weights occupy 461,056 bytes, input 16,384 bytes,
output 8,192 bytes; at most 65,536 bytes of two successive layer output buffers are
live (excluding input, NumPy metadata, finite-check temporaries, source-weight copies
and allocator overhead). The scalar C++ kernels themselves allocate no heap memory.
Noncontiguous inputs require an additional contiguous input copy. PE allocates its
output, with no additional native heap buffer. The report's buffer bounds are
analytical accounting, distinguished from measured RSS.

## Integration plan and next migration boundary

1. **Exact environment gate:** repeat against the pinned exporter versions and all
   three native platforms; retain version/build metadata and tolerance failures.
2. **Checkpoint subset gate:** add a reviewed state_dict-to-weight adapter with
   explicit names/shapes/dtypes and safetensors validation. Compare real projection
   weights and activations. Do not execute arbitrary checkpoint pickle data.
3. **Next operator tranche:** standalone PositionEmbedding addition/broadcast, ReLU
   and SiLU, then Conv1d plus residual blocks. Add stride/padding/dilation, token-mask,
   normalization epsilon and eval-statistics fixtures before decoder integration.
   Transformer attention and the stochastic token sampler remain out of phase two.
4. **ONNX composition:** represent the same primitives with standard ONNX Constant,
   MatMul/Gemm, Add and LeakyRelu nodes; PE can be a precomputed constant. Test those
   small graphs using ORT CPU against both Torch and PyIgnite before attempting an
   alternative graph exporter. A C++ ORT custom op is possible but unnecessary for
   primitives ORT already supports and would add deployment complexity.
5. **Full-model gate:** compare intermediate activations and the six-input G1
   output contract with `motionbricks.cpu_reference`. That executor hash-gates the
   released model; a new exported artifact must get separate identity/contract
   review, never bypass the hash check. This work did **not execute** the real
   approximately 734 MB G1 FP32 graph. Hydrating a model is not validation.
6. **Performance gate:** profile before adding a BLAS/SIMD dependency, include
   warm/cold latency and allocation measurements, and preserve scalar reference
   tests. No production switch until full-model tolerances, discrete decisions,
   platform results and performance justify it.

The original exporter remains the baseline and rollback path. Two primitive ports
establish neither a general Torch replacement nor end-to-end MotionBricks parity.

## Licensing

The semantics derive from the Apache-2.0 NVIDIA shared layer source; its upstream
T2M-GPT and MotionGPT notices remain in `tools/onnx/licenses` and `layers.py`.
PyIgnite additions use the repository Apache-2.0 license. No model weights or
third-party runtime binaries are added to this prototype.
