# Unitree G1 CPU ONNX reference

This standalone graph executor supports the released **G1 FP32 model, batch 1**.
It uses NumPy and ONNX Runtime's `CPUExecutionProvider`, without importing Warp,
TensorRT, Newton, JAX or CUDA. It does not replace the interactive runtime, implement
TPU inference, or change the hardware boundaries in the
[TPU integration protocol](tpu_integration_protocol.md).

## Isolated installation

From a source checkout, use Python 3.12 or 3.13. Do not run root `uv sync` or
`pip install .`: the full application still has CUDA dependencies.

```sh
python3.12 -m venv .venv-cpu-reference
. .venv-cpu-reference/bin/activate
python -m pip install -r tools/cpu_reference/requirements.txt
python -m unittest discover -s tests/cpu_reference -v
python -m motionbricks.cpu_reference --validate-only
```

The dependency file pins NumPy 2.3.5 and ONNX Runtime 1.23.2 as a reproducible
installation target. Offline CI installs only NumPy; it does not establish ORT
wheel availability or real inference on every CI platform. No Apple M6 or TPU
hardware support is claimed. Run from the repository root; no package installation
or GPU discovery occurs. NumPy is required even for contract-only checks; ORT is
imported only when opening a hydrated, hash-verified model.

## Run the real released graph

Download only the required model, under its existing
[NVIDIA Open Model Agreement notice](../motionbricks/assets/onnx/LICENSE.md):

```sh
git lfs pull --include="motionbricks/assets/onnx/unitree_g1/mmm_v6_g1_fp32.onnx" --exclude=""
python -m motionbricks.cpu_reference \
  --model motionbricks/assets/onnx/unitree_g1/mmm_v6_g1_fp32.onnx \
  --token-count 6 --repeat 2 --threads 1 --outputs /tmp/g1-output.npz \
  > /tmp/g1-report.json
```

The approximately 734 MB graph must be hydrated; an LFS pointer is not a model.
The executor checks SHA-256 against the released FP32 LFS object:
`79258d3613988b74ab84a530352ea600bbe78a1048584f059e231e44641cea16`.
Renaming the mixed FP16 graph cannot bypass this check. Other exports are rejected;
admitting a new model requires deliberate identity/contract review and tests.
Keep the model file immutable during session construction. This release is a
single-file model; external-data ONNX variants are not supported.

The default fixture is a deterministic stationary pose, with root height 0.75 m,
identity XYZW quaternion, zero joint angles, all conditioning masks enabled and
one allowed prediction length. It exercises the graph, not motion quality or robot
stability. To use prepared model-space tensors, pass `--inputs request.npz` with
exactly the six named arrays. `--token-count` applies only to the synthetic fixture.
NPZ loading disables pickle. Input preparation must follow the
[G1 model card](unitree_g1_model.md); units, joint order, coordinate alignment and
physical joint limits cannot be inferred from a generic numeric tensor.

For the opt-in real integration test:

```sh
MOTIONBRICKS_CPU_ONNX_MODEL="$PWD/motionbricks/assets/onnx/unitree_g1/mmm_v6_g1_fp32.onnx" \
  python -m unittest discover -s tests/cpu_reference -v
```

Without this environment variable the real test reports `G1 BLOCKED` as a unittest
skip. With explicit opt-in, missing files/dependencies, invalid graphs and inference
failures are test failures, not skips. The CLI exits 0 on success, 2 for missing
model/dependency prerequisites (`BLOCKED`), and 1 for invalid requests, wrong model
identity, initialization/execution errors or invalid outputs (`FAILED`). Argument
syntax errors use argparse's exit 2. No automatic model download or fallback occurs.

## Python graph interface

```python
from motionbricks.cpu_reference import CPUReference, synthetic_request, valid_frames

request = synthetic_request(token_count=16)
with CPUReference(threads=1) as reference:
    outputs, report = reference.run(request)
    raw = valid_frames(outputs, request)  # [1, 64, 36] for 16 tokens
    trimmed = valid_frames(outputs, request, trim_boundaries=True)  # [1, 58, 36]
```

The checked-in [manifest](../motionbricks/assets/onnx/unitree_g1/unitree_g1_n1.json)
is authoritative for names, shapes, dtypes and token lengths. Validation rejects:

- Missing/extra names, non-arrays, wrong dtypes/ranks/dimensions or batch other than 1.
- Nonbinary INT32 masks and an empty allowed-length set. Conditioning masks remain
  independent: there is no invented requirement that all three match or be all-on.
- NaN/Inf in any input or output, including unused padding, and zero input root
  quaternions even in masked slots. No silent casts or quaternion normalization.
- Output counts outside 6–16 or outside the request's allowed set, mismatched output
  capacity, and graph metadata that disagrees with the manifest. Only the graph's
  leading batch dimension may be symbolic.

All four target slots are explicit graph inputs. The caller must pack/mask 1–4
logical targets using the existing semantics; this module does not implement a
runtime pose adapter or infer target count from masks. Raw outputs have capacity
64, with `4 * pred_num_tokens` valid frames. Trimming three from each end leaves
18–58 frames. The helper returns owned copies of both poses and contacts, without
alignment, smoothing, root restoration, contact clipping or endpoint correction.
Raw contacts are checked for finiteness, not clamped to [0,1]. A future decoded
adapter must validate its own contact/pose semantics.

Calls are synchronous and serialized per instance. Input buffers are copied before
ORT execution; callers must not mutate them concurrently with validation/copying.
Returned outputs do not alias subsequent requests. `close()` waits for an active
run, drops the owned ORT session reference, and is idempotent. Calls after close
fail. ORT's Python API has no public explicit destructor; this does not promise
that the operating system immediately returns every allocator page. Use `with`
for cleanup even when a request raises. An execution error is propagated; it never
switches provider or silently returns an older output.

## Evidence and validation gates

| Evidence | Meaning | Limit |
| --- | --- | --- |
| `CONTRACT_ONLY` / G0 input validation | Input names, shapes, masks, lengths and values validated | No inference |
| Offline suite | Synthetic outputs and explicitly fake ORT sessions test errors, isolation, serialization and release | G0 graph-boundary coverage only; not full pose-adapter admission |
| `REAL_CPU_INFERENCE` / G1 single request | Hash-verified real weights executed synchronously on CPU; outputs validated | A smoke fixture is not the full protocol admission corpus |
| Cross-backend parity `NOT_TESTED` | No candidate backend compared | G2–G5 remain unvalidated |

Real runs record OS, CPU architecture/processor string, Python/NumPy/ORT versions,
model and manifest SHA-256, canonical input/output tensor hashes, provider, thread
settings, execution/optimization policy, session-load time, each synchronized
`session.run` time and valid lengths. CPU model strings can be empty on some OSes;
retain the actual host inventory separately when comparing machines. Hashes include
names, dtypes, shapes and little-endian C-order bytes, not NPZ container metadata.

The CLI repeats identical inputs and requires byte-identical outputs within that
session. The real test alternates counts 6, 16, 6 and checks exact repeat equality,
lengths and closure. This is distinct from cross-backend tolerance-based parity.
Timing excludes input/output validation, copies, hashing and pose adapters. First
and subsequent requests are listed separately, without a warm-up or benchmark
claim. Graph optimizations are disabled and thread count defaults to one to keep
the reference conservative; neither deterministic hashes across different CPUs/
ORT versions nor a real-time deadline is promised.

For full protocol advancement, collect a fixed valid corpus including target
counts 1–4, moving poses, mixed allowed sets, translations and rotations; preserve
input/output hashes and later compare raw valid frames before any correction.
This PR supplies a minimal G1 executor, not the protocol's 100-request-per-rig,
SOMA, decoded-parity, chained-motion, TPU or performance admission evidence.

## Implementation validation (2026-11-01)

Local Python 3.12.14 / NumPy 2.3.5 validation: 13 new offline tests passed,
31 existing preflight tests passed, and one example-source test passed. One real
CPU test and two GPU example tests skipped. ONNX Runtime 1.23.2 installed and
imported successfully on the Linux x86_64 host; this is dependency evidence only. The real 734 MB model was not downloaded or executed during
implementation. G1 real-weight execution is **BLOCKED / unverified** in this review;
no CPU inference performance, TPU execution or cross-backend numerical result is
claimed. The six-combination OS/Python CI matrix is configured to run G0 tests without
model weights; consult the PR checks for its actual result.
