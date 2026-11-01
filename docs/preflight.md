# CPU-safe preflight and reproducibility

See [platform safety](platform_safety.md) for Ubuntu/macOS behavior, bounded subprocesses, input limits, and the opt-in example launcher.

Run from the repository root with a system Python, without `uv run` or installing
MotionBricks. The checker uses only the standard library (Python 3.11+ for the
diagnostic tool; the **runtime still requires Python 3.12+**).

```sh
python tools/preflight.py --model soma
python tools/preflight.py --model unitree_g1 --precision fp16 --json
python -m unittest discover -s tests/preflight -v
python -m unittest discover -s tests/examples -v
```

The default mode does not initialize CUDA, import TensorRT/Warp, download assets,
build engines, or run inference. It checks Python, the project's dependency pins,
installed package versions, both selected model manifest and selected precision,
Git LFS availability, model weights and assets used by the two headless examples.
Missing dependencies and resources are reported even when working offline.
The current manifest schema/timing and tensor metadata structure are checked;
this is not verification of the ONNX graph's actual tensor contract.

Assets are checked for missing/empty files and unhydrated LFS pointers. Hydrated
assets are streamed through SHA-256 and checked against `git show HEAD:<path>`'s
LFS hash and size. Source archives without Git history produce WARN for unverifiable
assets, not a false integrity PASS. A valid hash proves byte identity only.
The check covers the selected ONNX model, walk/jog clips, and SOMA skeleton;
it does not certify every optional viewer/robot mesh asset in the repository.

## Status and exit codes

- `PASS`, `FAIL`, `WARN`, and `SKIP` describe individual checks.
- Default exit 0 means **offline configuration and any supplied pose JSON are valid**.
  Missing CUDA, packages, or LFS data can still appear as runtime FAILs. Exit 1 means
  an offline check failed; argparse usage errors return 2.
- `--probe-gpu` queries the CUDA driver and imports TensorRT and Warp in bounded
  subprocesses. `--require-runtime` implies these probes and returns 1 unless
  **every reported prerequisite is PASS** (including file integrity).
- `runtime_prerequisites_verified` never means model inference succeeded. The
  checker always reports `inference: NOT_RUN` and `perception: NOT_TESTED`.

Unsupported OS/architecture combinations skip native probes and fail strict runtime admission. The CUDA driver probe runs in a bounded subprocess.

The driver probe requires CUDA driver API >=12000 and at least one visible device;
this is a baseline check, not a guarantee of compatibility with every GPU or Warp
version. TensorRT import and Warp's actual CUDA visibility are separate checks.
`nvidia-smi`'s displayed CUDA version would not prove a toolkit is installed.
No compiler/toolkit installation is inferred or required by this preflight.
Full engine construction remains the final compatibility test.

## Pose JSON (CPU only)

```sh
python tools/preflight.py --model unitree_g1 --poses poses.json
```

The envelope has `model`, `joint_names`, `context`, and `target` keys. These are
**runtime poses**, not raw ONNX inputs or the source CSV format. Context has exactly
4 frames; target has 1–4. Values must be finite float32-compatible numbers, not
booleans or strings. Quaternions must be unit XYZW (norm tolerance 0.001).

| Rig | Per-frame shape | Meaning |
| --- | --- | --- |
| SOMA | `[J, 7]` | Local transforms: XYZ meters + XYZW quaternion; Hips first |
| Unitree G1 | `[36]` | Root XYZ meters + XYZW quaternion + 29 angles in radians |

G1 joint names must exactly match its manifest order. SOMA names must be unique,
include the 30 manifest joints, and begin with Hips; additional skeleton joints
are accepted. Model space is SOMA Y-up or G1 Z-up/+X-forward. Converted world-space
poses must use a consistent `model_to_runtime` transform in the engine. JSON cannot
prove units, coordinate conventions, anatomical proportions, physical feasibility,
or that the caller labeled joints correctly. Validation does not normalize or
silently repair data and does not send it to a robot.

Generate a small **synthetic format-only** G1 fixture (not a safe robot command):

```sh
python - <<'PY'
import json
from pathlib import Path
manifest = json.loads(Path('motionbricks/assets/onnx/unitree_g1/unitree_g1_n1.json').read_text())
pose = [0, 0, 0, 0, 0, 0, 1] + [0] * 29
Path('poses.json').write_text(json.dumps({
    'model': 'unitree_g1', 'joint_names': manifest['joint_names'],
    'context': [pose] * 4, 'target': [pose],
}))
PY
```

## Real GPU execution (explicit opt-in)

Use a supported NVIDIA GPU with a compatible driver, Python >=3.12, the project
runtime dependencies (including all three TensorRT CUDA 12 packages pinned to
10.8.0.43), and hydrated LFS assets. RTX 4090 is the upstream tested example,
not an assumption about the user's hardware. Follow the README installation:

```sh
git lfs pull
uv sync
uv run python tools/preflight.py --model soma --require-runtime
uv run python tools/preflight.py --model unitree_g1 --require-runtime
# Run this only after BOTH strict checks exit 0:
MOTIONBRICKS_ENGINE_TESTS=1 uv run python -m unittest discover -s tests/examples -v
```

On PowerShell set `$env:MOTIONBRICKS_ENGINE_TESTS = '1'` before the last command.
The examples run FP32 for both rigs and check two chained generations (18–58 valid
frames each) and a locomotion left turn. First builds can take minutes and create
`.trt-cache`; each example subprocess has an existing 1800-second timeout.

Without opt-in, two example tests skip. With opt-in but unavailable prerequisites,
the example class skips with reasons **before loading runtime modules**. Once
prerequisites pass, example errors are failures, never converted to skips. For GPU
CI use the strict checks as mandatory preceding steps so a skip cannot count as
successful GPU validation. The added GitHub workflow runs CPU tests only, without
LFS hydration or project dependencies.

The repository's full `tests/test_all.py` discovers app, runtime, renderer, and
engine suites, some of which import NumPy/Warp/Newton before any skip decorator.
It is not a dependency-free test entry point. `test_real_engines.py` additionally
covers FP32/FP16 and requires the full runtime; it is outside this CPU-safe subset.

Motion generation, even when successfully tested, does not demonstrate human-like
force sensation, temperature perception, feedback control, or safe hardware motion.

## Actual local validation — 2026-11-01

Base inspected: `54fc563aeaaf819a753d72cc9fdc6713989cdd43` of
`wu709621493/motionbricks`, branch `main`. Source was cloned with
`GIT_LFS_SKIP_SMUDGE=1`; no large model download or runtime install was performed.

- Linux x86-64, Python 3.12.14; Git LFS 3.4.1 available.
- CPU unit suite: 16 tests passed (including both rigs, frame/shape/numeric errors,
  quaternion checks, LFS integrity, missing executables, timeouts, and exit codes).
- Existing examples: source compilation passed; 2 GPU tests skipped by default.
- Explicit engine-test opt-in: source compilation passed; GPU class skipped for
  missing prerequisites before any example subprocess ran.
- Both model manifests checked; selected FP32/FP16 weights are unhydrated pointers.
- CUDA driver library `libcuda.so.1`, TensorRT, and Warp unavailable in this execution
  environment. This says nothing about the user's own computer's hardware.
- Strict runtime check returned 1 as intended. No engine build, inference, motion
  quality/latency benchmark, full-suite run, or hardware validation was completed.
- GitHub Actions configuration supplied; remote CI status is separate from these
  local results. No remote success is claimed here.
