"""Independent, synchronous G1 FP32 graph reference; no pose/world adapter."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import threading
import time
from pathlib import Path

import numpy as np

ASSETS = Path(__file__).parent / "assets" / "onnx" / "unitree_g1"
MANIFEST = ASSETS / "unitree_g1_n1.json"
# Identity of the released FP32 graph, from its checked-in Git LFS pointer.
# Interface dtypes alone cannot distinguish this graph from mixed FP16.
MODEL_SHA256 = "79258d3613988b74ab84a530352ea600bbe78a1048584f059e231e44641cea16"


class ContractError(ValueError):
    """A request, graph interface, or result violates the G1 contract."""


class PrerequisiteError(RuntimeError):
    """G1 is BLOCKED: a required dependency or hydrated asset is missing."""


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tensor_hash(arrays):
    """Canonical hash includes names, dtype, shape and little-endian C-order bytes."""
    digest = hashlib.sha256()
    for name, array in sorted(arrays.items()):
        value = np.asarray(array, dtype=array.dtype.newbyteorder("<"), order="C")
        header = json.dumps([name, value.dtype.str, list(value.shape)], separators=(",", ":"))
        digest.update(header.encode() + b"\0")
        digest.update(value.tobytes())
    return digest.hexdigest()


class G1Contract:
    def __init__(self):
        self.manifest = json.loads(MANIFEST.read_text())
        self.manifest_hash = file_hash(MANIFEST)
        self.inputs = {s["name"]: s for s in self.manifest["tensor_specs"] if s["mode"] == "input"}
        self.outputs = {s["name"]: s for s in self.manifest["tensor_specs"] if s["mode"] == "output"}

    def _validate(self, arrays, specs):
        if set(arrays) != set(specs):
            raise ContractError(f"Tensor names: expected {sorted(specs)}, got {sorted(arrays)}")
        for name, spec in specs.items():
            value = arrays[name]
            if not isinstance(value, np.ndarray):
                raise ContractError(f"{name}: expected numpy.ndarray")
            if value.shape != tuple(spec["shape"]):
                raise ContractError(f"{name}: expected shape {spec['shape']} (batch 1), got {value.shape}")
            if value.dtype != np.dtype(spec["dtype"]):
                raise ContractError(f"{name}: expected {spec['dtype']}, got {value.dtype}")
            if not np.isfinite(value).all():
                raise ContractError(f"{name}: NaN/Inf is not allowed, including padding")

    def validate_inputs(self, arrays):
        self._validate(arrays, self.inputs)
        for name, spec in self.inputs.items():
            if spec["dtype"] == "int32" and not np.isin(arrays[name], [0, 1]).all():
                raise ContractError(f"{name}: mask values must be 0 or 1")
        if not arrays["allowed_pred_num_tokens"].any():
            raise ContractError("At least one prediction length must be enabled")
        for name in ("context_qpos", "target_qpos"):
            if np.any(np.all(arrays[name][..., 3:7] == 0, axis=-1)):
                raise ContractError(f"{name}: zero root quaternion, including masked slots")

    def validate_outputs(self, arrays, inputs):
        self.validate_inputs(inputs)
        self._validate(arrays, self.outputs)
        count = int(arrays["pred_num_tokens"][0])
        lo, hi = self.manifest["min_pred_tokens"], self.manifest["max_pred_tokens"]
        if not lo <= count <= hi or not inputs["allowed_pred_num_tokens"][0, count - lo]:
            raise ContractError(f"pred_num_tokens: {count} is not an allowed length")
        return self.manifest["frames_per_token"] * count

    def validate_session(self, session):
        for nodes, specs in ((session.get_inputs(), self.inputs), (session.get_outputs(), self.outputs)):
            if len(nodes) != len(specs) or {n.name for n in nodes} != set(specs):
                raise ContractError("Graph tensor names do not match manifest")
            for node in nodes:
                spec = specs[node.name]
                dtype = {"float32": "tensor(float)", "int32": "tensor(int32)"}[spec["dtype"]]
                shape = node.shape
                if node.type != dtype or len(shape) != len(spec["shape"]):
                    raise ContractError(f"Graph type/rank mismatch: {node.name}")
                # Only batch may be symbolic. The supported request remains N=1.
                if (isinstance(shape[0], int) and shape[0] != 1) or list(shape[1:]) != spec["shape"][1:]:
                    raise ContractError(f"Graph shape mismatch: {node.name}: {shape}")


def synthetic_request(token_count=6):
    """Deterministic stationary graph fixture, not a validated robot pose/adapter."""
    contract = G1Contract()
    if type(token_count) is not int or not 6 <= token_count <= 16:
        raise ContractError("token_count must be an integer from 6 through 16")
    arrays = {name: np.zeros(s["shape"], dtype=s["dtype"]) for name, s in contract.inputs.items()}
    for name in ("context_qpos", "target_qpos"):
        arrays[name][..., 2] = 0.75
        arrays[name][..., 6] = 1.0
    for name in ("has_global_root_values", "has_local_root_values", "has_local_poses"):
        arrays[name][:] = 1
    arrays["allowed_pred_num_tokens"][0, token_count - 6] = 1
    return arrays


def valid_frames(outputs, inputs, *, trim_boundaries=False):
    """Copy valid raw frames; optional trimming is NOT runtime endpoint correction."""
    length = G1Contract().validate_outputs(outputs, inputs)
    frames = slice(3, length - 3) if trim_boundaries else slice(0, length)
    return {name: outputs[name][:, frames].copy()
            for name in ("pred_qpos", "pred_foot_contacts")}


class CPUReference:
    """Serializes run/close; outputs are request-owned copies. No fallback."""
    def __init__(self, model_path=None, *, threads=1):
        if type(threads) is not int or threads < 1:
            raise ValueError("threads must be a positive integer")
        self._lock = threading.Lock()
        self._session = None
        self.contract = G1Contract()
        path = Path(model_path) if model_path else ASSETS / self.contract.manifest["onnx_filename"]
        if not path.is_file():
            raise PrerequisiteError(f"Missing ONNX file: {path}")
        with path.open("rb") as stream:
            if stream.read(128).startswith(b"version https://git-lfs.github.com/spec/v1"):
                raise PrerequisiteError("ONNX file is a Git LFS pointer; hydrate the FP32 model first")
        model_hash = file_hash(path)
        if model_hash != MODEL_SHA256:
            raise ContractError("Model SHA-256 is not the released G1 FP32 artifact; no precision inferred from IO")
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise PrerequisiteError("Install optional onnxruntime in the isolated CPU environment") from exc
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        start = time.perf_counter()
        try:
            session = ort.InferenceSession(str(path), sess_options=options, providers=["CPUExecutionProvider"])
            session.disable_fallback()
            if session.get_providers() != ["CPUExecutionProvider"]:
                raise ContractError("Session is not CPU-only")
            self.contract.validate_session(session)
        except Exception as exc:
            raise RuntimeError(f"CPU session initialization failed: {exc}") from exc
        self._session = session
        self.metadata = {
            "device": "CPU", "providers": session.get_providers(), "os": platform.platform(),
            "architecture": platform.machine(), "processor": platform.processor(),
            "python": platform.python_version(), "numpy": np.__version__, "onnxruntime": ort.__version__,
            "model_sha256": model_hash, "manifest_sha256": self.contract.manifest_hash,
            "rig": "unitree_g1", "batch_size": 1, "precision": "released FP32 graph",
            "intra_op_threads": threads, "inter_op_threads": 1,
            "execution_mode": "ORT_SEQUENTIAL", "graph_optimization": "ORT_DISABLE_ALL",
            "session_load_seconds": time.perf_counter() - start,
        }

    def run(self, inputs):
        with self._lock:
            if self._session is None:
                raise RuntimeError("CPU reference is closed")
            self.contract.validate_inputs(inputs)
            owned = {name: value.copy(order="C") for name, value in inputs.items()}
            names = list(self.contract.outputs)
            start = time.perf_counter()
            try:
                values = self._session.run(names, owned)
            except Exception as exc:
                raise RuntimeError(f"CPU inference failed: {exc}") from exc
            elapsed = time.perf_counter() - start
            if len(values) != len(names):
                raise ContractError("Graph returned the wrong output count")
            outputs = {name: np.array(value, copy=True) for name, value in zip(names, values)}
            frames = self.contract.validate_outputs(outputs, owned)
            report = dict(self.metadata, evidence="REAL_CPU_INFERENCE", gate="G1_SINGLE_REQUEST",
                          cross_backend_parity="NOT_TESTED", input_sha256=tensor_hash(owned),
                          output_sha256=tensor_hash(outputs), inference_seconds=elapsed,
                          raw_frames=frames, trimmed_frames=frames - 6)
            return outputs, report

    def close(self):
        # ORT's Python API has no public close: drop the sole owned session reference.
        with self._lock:
            self._session = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true", help="Synthetic G0 input check; no model inference")
    parser.add_argument("--model", type=Path)
    parser.add_argument("--inputs", type=Path, help="NPZ containing exactly the six graph inputs")
    parser.add_argument("--token-count", type=int, default=6, choices=range(6, 17))
    parser.add_argument("--repeat", type=int, default=2)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--outputs", type=Path, help="Save last raw output tensors as NPZ")
    args = parser.parse_args(argv)
    try:
        if args.repeat < 1:
            raise ValueError("repeat must be positive")
        if args.validate_only and args.outputs:
            raise ValueError("--outputs requires real inference")
        if args.inputs:
            with np.load(args.inputs, allow_pickle=False) as data:
                inputs = {name: data[name] for name in data.files}
        else:
            inputs = synthetic_request(args.token_count)
        G1Contract().validate_inputs(inputs)
        if args.validate_only:
            result = {"evidence": "CONTRACT_ONLY", "gate": "G0_INPUT_VALIDATION",
                      "input_sha256": tensor_hash(inputs), "G1": "NOT_RUN", "cross_backend_parity": "NOT_TESTED"}
        else:
            reports = []
            with CPUReference(args.model, threads=args.threads) as reference:
                for _ in range(args.repeat):
                    outputs, report = reference.run(inputs)
                    reports.append(report)
            if len({r["output_sha256"] for r in reports}) != 1:
                raise ContractError("Identical repeated request produced different output bytes")
            if args.outputs:
                np.savez(args.outputs, **outputs)
            result = {"evidence": "REAL_CPU_INFERENCE", "runs": reports,
                      "repeat_exact": True, "cross_backend_parity": "NOT_TESTED"}
        print(json.dumps(result, indent=2))
        return 0
    except PrerequisiteError as exc:
        print(json.dumps({"status": "BLOCKED", "gate": "G1", "error": str(exc)}))
        return 2
    except Exception as exc:
        print(json.dumps({"status": "FAILED", "error_type": type(exc).__name__, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
