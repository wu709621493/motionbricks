# SPDX-License-Identifier: Apache-2.0
"""Dependency-free diagnostics; never imports the MotionBricks runtime or runs inference."""
from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
try:
    import tomllib
except ModuleNotFoundError:
    raise SystemExit("Preflight needs Python >=3.11; MotionBricks runtime requires Python >=3.12.")

ROOT = Path(__file__).resolve().parents[1]
TRT_VERSION = "10.8.0.43"
RIGS = ("soma", "unitree_g1")


def command(args, cwd=None):
    try:
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0, (result.stdout or result.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)


def manifest(root, model):
    if model not in RIGS:
        raise ValueError(f"unknown model: {model}")
    path = root / "motionbricks/assets/onnx" / model / f"{model}_n1.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest must be a JSON object")
    expected = dict(schema_version=1, batch_size=1, sample_rate=30, frames_per_token=4,
                    context_frames=4, target_capacity=4, min_pred_tokens=6, max_pred_tokens=16)
    for key, value in expected.items():
        if data.get(key) != value:
            raise ValueError(f"{key} must be {value}")
    names = data["joint_names"]
    if (not isinstance(names, list) or len(names) != (30 if model == "soma" else 29)
            or not all(isinstance(n, str) and n for n in names) or len(set(names)) != len(names)):
        raise ValueError("invalid joint_names")
    for filename in (data["onnx_filename"], data["precision_variants"]["fp16"]["onnx_filename"]):
        if not isinstance(filename, str) or Path(filename).name != filename or not filename.endswith(".onnx"):
            raise ValueError("ONNX paths must be local filenames")
    specs = data["tensor_specs"]
    if not isinstance(specs, list) or not specs:
        raise ValueError("tensor_specs must be nonempty")
    tensor_names = []
    for spec in specs:
        if (not isinstance(spec, dict) or not isinstance(spec.get("name"), str)
                or not spec["name"] or spec.get("mode") not in ("input", "output")
                or spec.get("dtype") not in ("float32", "int32")
                or not isinstance(spec.get("shape"), list) or not spec["shape"]
                or not all(type(d) is int and d > 0 for d in spec["shape"])):
            raise ValueError("invalid tensor spec")
        tensor_names.append(spec["name"])
    if len(set(tensor_names)) != len(tensor_names):
        raise ValueError("duplicate tensor names")
    return path, data


def validate_poses(payload, model, joint_names):
    """Validate JSON runtime poses, not raw ONNX features or G1 CSV source units.

    SOMA supports additional skeleton joints; model joints must be present and Hips first.
    Coordinates are meters, G1 angles radians, quaternions XYZW (unit tolerance 1e-3).
    """
    if model not in RIGS or not isinstance(payload, dict) or payload.get("model") != model:
        raise ValueError("payload model must match selected model")
    names = payload.get("joint_names")
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        raise ValueError("joint_names must be a list of strings")
    if model == "soma":
        if not names or names[0] != "Hips" or len(set(names)) != len(names) or not set(joint_names) <= set(names):
            raise ValueError("SOMA needs all model joints, unique names, and Hips first")
    elif names != joint_names:
        raise ValueError("G1 joint_names must match manifest order")

    def vector(value, length, location):
        if not isinstance(value, list) or len(value) != length:
            raise ValueError(f"{location}: expected {length} values")
        for x in value:
            try:
                valid = type(x) in (int, float) and math.isfinite(x) and abs(x) <= 3.402823466e38
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError(f"{location}: expected finite float32-compatible numbers")
        q = value[3:7]
        if abs(math.hypot(*q) - 1) > 1e-3:
            raise ValueError(f"{location}: quaternion must have unit length (XYZW)")

    for field in ("context", "target"):
        poses = payload.get(field)
        if not isinstance(poses, list) or not (len(poses) == 4 if field == "context" else 1 <= len(poses) <= 4):
            raise ValueError(f"{field}: expected {'4' if field == 'context' else '1–4'} poses")
        for i, pose in enumerate(poses):
            if model == "soma":
                if not isinstance(pose, list) or len(pose) != len(names):
                    raise ValueError(f"{field}[{i}]: joint count mismatch")
                for j, transform in enumerate(pose):
                    vector(transform, 7, f"{field}[{i}][{j}]")
            else:
                vector(pose, 36, f"{field}[{i}]")


def asset_status(path, root):
    """Verify hydrated bytes against the committed LFS pointer when available."""
    try:
        with path.open("rb") as stream:
            prefix = stream.read(256)
        if not prefix:
            return "FAIL", "empty file"
        if prefix.startswith(b"version https://git-lfs.github.com/spec/v1"):
            return "FAIL", "unhydrated Git LFS pointer; run git lfs pull"
        ok, pointer = command(["git", "show", f"HEAD:{path.relative_to(root).as_posix()}"], root)
        match = re.search(r"oid sha256:([0-9a-f]{64})\nsize (\d+)", pointer) if ok else None
        if not match:
            return "WARN", "present, but no committed LFS size/hash available; integrity unverified"
        if path.stat().st_size != int(match[2]):
            return "FAIL", "size differs from committed LFS pointer"
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != match[1]:
            return "FAIL", "SHA-256 differs from committed LFS pointer"
        return "PASS", "size and SHA-256 match committed LFS pointer (not an ONNX load test)"
    except OSError as exc:
        return "FAIL", str(exc)


def cuda_probe():
    """Query the CUDA driver directly; nvidia-smi's advertised version is not a toolkit."""
    try:
        driver = ctypes.CDLL("nvcuda.dll" if os.name == "nt" else (ctypes.util.find_library("cuda") or "libcuda.so.1"))
        code = driver.cuInit(0)
        if code:
            return "FAIL", f"cuInit returned {code}"
        version, count = ctypes.c_int(), ctypes.c_int()
        for name, value in (("cuDriverGetVersion", version), ("cuDeviceGetCount", count)):
            code = getattr(driver, name)(ctypes.byref(value))
            if code:
                return "FAIL", f"{name} returned {code}"
        ok = version.value >= 12000 and count.value > 0
        return ("PASS" if ok else "FAIL"), f"driver API {version.value}; visible CUDA devices {count.value}"
    except (OSError, AttributeError) as exc:
        return "FAIL", str(exc)


def inspect(root=ROOT, model="soma", precision="fp32", probe_gpu=False):
    root = Path(root).resolve()
    checks = []
    def add(name, status, detail, scope="runtime"):
        checks.append(dict(name=name, status=status, detail=detail, scope=scope))
    add("python", "PASS" if sys.version_info >= (3, 12) else "FAIL", sys.version.split()[0])
    try:
        project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
        required = [f"{n}=={TRT_VERSION}" for n in ("tensorrt-cu12", "tensorrt-cu12-bindings", "tensorrt-cu12-libs")]
        if project["requires-python"] != ">=3.12" or not set(required) <= set(project["dependencies"]):
            raise ValueError("Python/TensorRT requirements changed; review preflight expectations")
        add("project_config", "PASS", "Python >=3.12; TensorRT CUDA 12 components pinned", "offline")
        path, data = manifest(root, model)
        add("manifest", "PASS", str(path.relative_to(root)), "offline")
        for requirement in project["dependencies"]:
            match = re.fullmatch(r"([\w-]+)(==|>=)([0-9.]+)", requirement)
            if not match:
                add("dependency", "WARN", f"unsupported requirement syntax: {requirement}")
                continue
            name, operator, expected = match.groups()
            if name.startswith("tensorrt-"):
                continue  # Checked separately below, including all three CUDA 12 packages.
            try:
                version = importlib.metadata.version(name)
                if operator == "==":
                    valid = version == expected
                else:
                    # Current project lower bounds are plain numeric releases.
                    valid = bool(re.fullmatch(r"[0-9.]+", version)) and tuple(map(int, version.split("."))) >= tuple(map(int, expected.split(".")))
                add(name, "PASS" if valid else "FAIL", f"installed {version}; requires {operator}{expected}")
            except importlib.metadata.PackageNotFoundError:
                add(name, "FAIL", f"not installed; requires {operator}{expected}")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        add("config", "FAIL", str(exc), "offline")
        data = None
    ok, detail = command(["git", "lfs", "version"], root)
    add("git_lfs", "PASS" if ok else "WARN", detail)
    for name in ("tensorrt-cu12", "tensorrt-cu12-bindings", "tensorrt-cu12-libs"):
        try:
            version = importlib.metadata.version(name)
            add(name, "PASS" if version == TRT_VERSION else "FAIL", f"installed {version}; expected {TRT_VERSION}")
        except importlib.metadata.PackageNotFoundError:
            add(name, "FAIL", "not installed; use the repository's uv sync installation")
    if data:
        filename = data["onnx_filename"] if precision == "fp32" else data["precision_variants"]["fp16"]["onnx_filename"]
        for asset in (path.with_name(filename),
                      root / f"assets/motions/{model}/locomotion/bs_1d_linear/Neutral_walk_forward_002__A057.{ 'bvh' if model == 'soma' else 'csv'}",
                      root / f"assets/motions/{model}/locomotion/bs_1d_linear/neutral_jog_ff_180_R_001__A534.{ 'bvh' if model == 'soma' else 'csv'}"):
            add(str(asset.relative_to(root)), *asset_status(asset, root))
        if model == "soma":
            asset = root / "motionbricks/assets/human/soma_base_skel_minimal_no_root.usd"
            add(str(asset.relative_to(root)), *asset_status(asset, root))
    if probe_gpu:
        add("cuda_driver", *cuda_probe())
        ok, detail = command([sys.executable, "-c", "import tensorrt as trt; print(trt.__version__); assert trt.__version__ == '10.8.0.43'"])
        add("tensorrt_import", "PASS" if ok else "FAIL", detail)
        ok, detail = command([sys.executable, "-c", "import warp as wp; wp.init(); assert wp.is_cuda_available(), 'No Warp CUDA device'; print(wp.get_cuda_device())"])
        add("warp_cuda", "PASS" if ok else "FAIL", detail)
    else:
        add("gpu_probes", "SKIP", "use --probe-gpu to query CUDA and import TensorRT/Warp")
    return dict(checks=checks, inference="NOT_RUN", perception="NOT_TESTED")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--model", choices=RIGS, default="soma")
    parser.add_argument("--precision", choices=("fp32", "fp16"), default="fp32")
    parser.add_argument("--poses", type=Path, help="optional runtime-pose JSON")
    parser.add_argument("--probe-gpu", action="store_true")
    parser.add_argument("--require-runtime", action="store_true", help="fail on runtime blockers or unverified checks; implies GPU probes")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = inspect(args.repo, args.model, args.precision, args.probe_gpu or args.require_runtime)
    if args.poses:
        try:
            _, data = manifest(args.repo, args.model)
            validate_poses(json.loads(args.poses.read_text()), args.model, data["joint_names"])
            status, detail = "PASS", "runtime pose layout and numeric values validated"
        except (OSError, ValueError, KeyError, TypeError) as exc:
            status, detail = "FAIL", str(exc)
        report["checks"].append(dict(name="poses", status=status, detail=detail, scope="offline"))
    report["offline_ok"] = all(c["status"] != "FAIL" for c in report["checks"] if c["scope"] == "offline")
    report["runtime_prerequisites_verified"] = all(c["status"] == "PASS" for c in report["checks"])
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for c in report["checks"]:
            print(f"{c['status']:4} {c['name']}: {c['detail']}")
        print("Inference NOT_RUN; human-like perception NOT_TESTED.")
    return int(not (report["runtime_prerequisites_verified"] if args.require_runtime else report["offline_ok"]))


if __name__ == "__main__":
    raise SystemExit(main())
