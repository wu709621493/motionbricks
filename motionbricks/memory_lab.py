"""Bounded CPU memory lab; logical shards are not physical DIMMs or a GPU.

Planning needs only the standard library. Execution needs NumPy and runs in a
supervised child with a deadline. No firmware, purchase, or remote-node access.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys

MIB = 1024**2
GIB = 1024**3
ROOT = Path(__file__).resolve().parents[1]
THREAD_VARIABLES = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
                    "VECLIB_MAXIMUM_THREADS", "BLIS_NUM_THREADS")


def integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in {low}..{high}")


@dataclass(frozen=True)
class RunConfig:
    logical_shards: int = 1000
    memory_mib: int = 64
    matrix_size: int = 32
    tile: int = 16
    rounds: int = 1
    threads: int = 1
    timeout_s: float = 60.0
    cache_sizes: tuple[int, ...] = (16, 64, 256, 1024)
    cache_repeats: int = 3
    render_path: str | None = None
    render_width: int = 1440
    render_height: int = 1000

    def __post_init__(self):
        for name, low, high in (("logical_shards", 1, 10000), ("memory_mib", 1, 65536),
                               ("matrix_size", 1, 128), ("tile", 1, 32),
                               ("rounds", 1, 100), ("threads", 1, 64),
                               ("cache_repeats", 1, 20),
                               ("render_width", 320, 1920), ("render_height", 320, 1440)):
            integer(getattr(self, name), name, low, high)
        if (type(self.timeout_s) not in (int, float) or
                not math.isfinite(self.timeout_s) or not 0 < self.timeout_s <= 3600):
            raise ValueError("timeout_s must be finite and in (0, 3600]")
        if type(self.cache_sizes) is not tuple or not 1 <= len(self.cache_sizes) <= 8:
            raise ValueError("cache_sizes must contain 1..8 matrix dimensions")
        for size in self.cache_sizes:
            integer(size, "cache size", 1, 2048)
        if self.render_path is not None:
            if type(self.render_path) is not str or not self.render_path.endswith(".png"):
                raise ValueError("render_path must be a PNG path")
        if self.memory_mib * MIB // (8 * self.logical_shards) < 3 * self.matrix_size**2:
            raise ValueError("each logical shard must hold its three float64 matrices")

    @property
    def estimated_bytes(self):
        # Payload + largest live sweep + independent reference fixtures + scratch
        # + import/BLAS allowance. This is a budget estimate, not a hard RSS cap.
        return (self.memory_mib * MIB + 3 * max(self.cache_sizes)**2 * 8
                + 7 * 3 * self.matrix_size**2 * 8 + 32 * MIB + 128 * MIB
                + (self.render_width * self.render_height * 32 if self.render_path else 0))


def build_plan(dimms=1000, dimm_gib=16):
    integer(dimms, "dimms", 1, 1000000)
    integer(dimm_gib, "dimm_gib", 1, 128)
    # Conservative CPU published limit, not the motherboard's newer-CPU maximum.
    per_node = min(8, 128 // dimm_gib)
    return {
        "schema_version": 1, "status": "PLAN_ONLY",
        "board": "ASUS ROG Rampage VI Extreme Encore",
        "cpu": "Intel Core i9-7980XE", "socket": "LGA2066",
        "slots_per_board": 8, "channels_per_cpu": 4,
        "cpu_published_max_gib": 128, "module_kind": "non-ECC unbuffered DDR4",
        "requested_physical_dimms": dimms, "dimm_capacity_gib": dimm_gib,
        "populated_dimms_per_full_node": per_node,
        "minimum_nodes_by_slots_and_capacity": math.ceil(dimms / per_node),
        "single_board_can_fit": dimms <= per_node,
        "raw_capacity_tib": dimms * dimm_gib / 1024,
        "balanced_channels_and_qvl_verified": False,
        "purchase_completed": False, "assembly_completed": False,
        "physical_inventory_verified": False, "distributed_backend_implemented": False,
    }


def shard_bounds(total_words, count):
    integer(total_words, "total_words", 1, 2**50)
    integer(count, "count", 1, min(total_words, 10000))
    return [(i * total_words // count, (i + 1) * total_words // count)
            for i in range(count)]


def cgroup_headrooms(root, relative="/"):
    """Read the visible v2 hierarchy, including finite parent limits."""
    root = Path(root).resolve()
    candidate = (root / relative.lstrip("/")).resolve()
    if not candidate.is_relative_to(root):
        return []
    paths = [root]
    while candidate != root:
        paths.append(candidate)
        candidate = candidate.parent
    results = []
    for directory in paths:
        try:
            current = int((directory / "memory.current").read_text())
        except (OSError, ValueError):
            continue
        for name in ("memory.max", "memory.high"):
            try:
                raw = (directory / name).read_text().strip()
                if raw != "max":
                    results.append(max(0, int(raw) - current))
            except (OSError, ValueError):
                pass
    return results


def available_memory():
    """Conservative snapshot; no claim that other processes cannot race it."""
    candidates, sources = [], []
    if sys.platform.startswith("linux"):
        try:
            data = Path("/proc/meminfo").read_text()
            match = re.search(r"^MemAvailable:\s+(\d+) kB", data, re.M)
            if match:
                candidates.append(int(match.group(1)) * 1024)
                sources.append("/proc/meminfo:MemAvailable")
        except OSError:
            pass
        try:
            groups = Path("/proc/self/cgroup").read_text().splitlines()
            relative = next((line[3:] for line in groups if line.startswith("0::")), "/")
            limits = cgroup_headrooms("/sys/fs/cgroup", relative)
            if limits:
                candidates.extend(limits)
                sources.append("visible_cgroup_v2_limits")
            # A common v1 mount; nested v1 layouts remain a documented limitation.
            v1 = Path("/sys/fs/cgroup/memory")
            if (v1 / "memory.limit_in_bytes").exists():
                limit = int((v1 / "memory.limit_in_bytes").read_text())
                used = int((v1 / "memory.usage_in_bytes").read_text())
                candidates.append(max(0, limit - used))
                sources.append("cgroup_v1_root_limit")
        except (OSError, ValueError):
            pass
    elif sys.platform == "darwin":
        try:
            text = subprocess.check_output(["vm_stat"], text=True, timeout=3)
            page = int(re.search(r"page size of (\d+) bytes", text).group(1))
            # Free + inactive only: deliberately excludes other reclaim estimates.
            counts = [int(re.search(rf"{label}:\s+(\d+)", text).group(1))
                      for label in ("Pages free", "Pages inactive")]
            candidates.append(sum(counts) * page)
            sources.append("vm_stat:free+inactive")
        except (OSError, subprocess.SubprocessError, AttributeError, ValueError):
            pass
    return {"available_bytes": min(candidates) if candidates else None, "sources": sources}


def budget_check(config, memory):
    available = memory["available_bytes"]
    if available is None:
        raise ValueError("available memory is unknown; refusing to allocate")
    limit = max(0, min(available // 2, available - 512 * MIB))
    if config.estimated_bytes > limit:
        raise ValueError(f"estimated {config.estimated_bytes} bytes exceeds budget {limit}")
    return {**memory, "estimated_worker_bytes": config.estimated_bytes,
            "admission_limit_bytes": limit, "hard_rss_limit_enforced": False}


def supervise(command, *, timeout_s, env=None):
    """Kill and reap the isolated worker on deadline/cancellation (POSIX only)."""
    if os.name != "posix":
        raise ValueError("execution supervisor currently requires POSIX")
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, cwd=ROOT, env=env, start_new_session=True)
    try:
        stdout, stderr = proc.communicate(timeout=timeout_s)
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.communicate()
        return {"status": "TIMEOUT" if isinstance(exc, subprocess.TimeoutExpired)
                else "CANCELLED", "worker_reaped": proc.returncode is not None}
    # The owned worker emits one bounded summary, never its allocated buffers.
    if len(stdout) > 128 * 1024 or len(stderr) > 16 * 1024:
        return {"status": "WORKER_OUTPUT_LIMIT", "worker_reaped": True}
    if proc.returncode:
        return {"status": "WORKER_FAILED", "returncode": proc.returncode,
                "detail": (stdout + stderr)[-4000:], "worker_reaped": True}
    try:
        result = json.loads(stdout)
        if type(result) is not dict or result.get("status") != "PASSED":
            raise ValueError("invalid success report")
    except (ValueError, TypeError):
        return {"status": "WORKER_PROTOCOL_ERROR", "worker_reaped": True}
    return {**result, "worker_reaped": True}


def run(config, power_trace=None):
    power = {"status": "NOT_PROVIDED", "live_monitoring": False}
    if power_trace is not None:
        from motionbricks.prebios_power import review_trace
        path = Path(power_trace)
        if path.stat().st_size > 4 * MIB:
            raise ValueError("power trace exceeds 4 MiB")
        power = {**review_trace(json.loads(path.read_text())), "live_monitoring": False}
        if power["status"] != "WITHIN_DECLARED_ENVELOPE":
            return {"status": "POWER_TRACE_REFUSED", "power_trace": power,
                    "worker_started": False}
    admission = budget_check(config, available_memory())
    env = os.environ.copy()
    env.update({key: str(config.threads) for key in THREAD_VARIABLES})
    result = supervise([sys.executable, "-m", "motionbricks.memory_lab_worker",
                        json.dumps(asdict(config))], timeout_s=config.timeout_s, env=env)
    return {**result, "schema_version": 1, "admission": admission,
            "power_trace": power, "config": asdict(config),
            "target_board_tested": False, "physical_dimm_count_verified": None,
            "gpu_used": False, "all_ram_tested": False, "all_cache_used_proven": False,
            "hardware_electrical_validated": False, "lifetime_proven": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--dimms", type=int, default=1000)
    plan.add_argument("--dimm-gib", type=int, default=16)
    execute = sub.add_parser("run")
    for flag, default in (("logical-shards", 1000), ("memory-mib", 64),
                          ("matrix-size", 32), ("tile", 16), ("rounds", 1),
                          ("threads", 1), ("cache-repeats", 3)):
        execute.add_argument("--" + flag, type=int, default=default)
    execute.add_argument("--timeout-s", type=float, default=60)
    execute.add_argument("--cache-sizes", type=int, nargs="+", default=[16, 64, 256, 1024])
    execute.add_argument("--power-trace", type=Path)
    execute.add_argument("--render", dest="render_path", type=str)
    execute.add_argument("--render-width", type=int, default=1440)
    execute.add_argument("--render-height", type=int, default=1000)
    args = parser.parse_args(argv)
    try:
        if args.mode == "plan":
            result = build_plan(args.dimms, args.dimm_gib)
        else:
            fields = vars(args).copy()
            fields.pop("mode")
            trace = fields.pop("power_trace")
            fields["cache_sizes"] = tuple(fields["cache_sizes"])
            if fields["render_path"]:
                fields["render_path"] = str(Path(fields["render_path"]).resolve())
            result = run(RunConfig(**fields), trace)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        result = {"status": "REFUSED", "detail": str(exc)}
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result["status"] in ("PLAN_ONLY", "PASSED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
