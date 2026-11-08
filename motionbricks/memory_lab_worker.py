"""CPU-only functional block executor. Not CUDA/PTX or a GPU timing model."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import platform
import resource
import statistics
import sys
import time

from motionbricks.memory_lab import (MIB, RunConfig, available_memory, budget_check,
                                     integer, shard_bounds)

CHUNK_WORDS = 131072
MASK = 0xA5A5C3C35A5A3C3C


def patterns(pool, bounds, *, write=False, invert=False):
    """Visit every 64-bit word with an address-derived pattern in bounded chunks."""
    import numpy as np
    bad = 0
    mask = MASK ^ ((2**64 - 1) if invert else 0)
    for lo, hi in bounds:
        for start in range(lo, hi, CHUNK_WORDS):
            end = min(hi, start + CHUNK_WORDS)
            expected = np.arange(start, end, dtype=np.uint64)
            np.bitwise_xor(expected, np.uint64(mask), out=expected)
            if write:
                pool[start:end] = expected
            else:
                bad += int(np.count_nonzero(pool[start:end] != expected))
    return bad


def fixtures(n, seed):
    """Independent scalar Python-integer oracle; no BLAS/tiled algorithm here."""
    import numpy as np
    a = [[(i * 3 + k + seed) % 7 - 3 for k in range(n)] for i in range(n)]
    b = [[(k + j * 2 + seed) % 5 - 2 for j in range(n)] for k in range(n)]
    c = [[sum(a[i][k] * b[k][j] for k in range(n)) for j in range(n)]
         for i in range(n)]
    return tuple(np.array(x, dtype=np.float64) for x in (a, b, c))


class CpuBlockRuntime:
    """Serial block scheduling; each output tile represents a block of lanes.

    Global arrays live in host RAM. Two copied tiles are the functional shared
    memory, and a tile accumulator represents lane-local accumulator registers.
    Stage ordering models load/compute barriers; it does not emulate GPU hardware.
    """
    def __init__(self, tile):
        integer(tile, "tile", 1, 32)
        self.tile = tile
        self.launches = self.blocks = self.load_phases = self.barriers = 0
        self.active_lanes = self.masked_lanes = 0
        self.state = "IDLE"

    def launch(self, a, b, c):
        import numpy as np
        if self.state != "IDLE":
            raise RuntimeError("runtime is not idle")
        if (a.ndim != 2 or b.shape != a.shape or c.shape != a.shape or
                a.shape[0] != a.shape[1]):
            raise ValueError("square, equally shaped matrices required")
        if any(x.dtype != np.float64 for x in (a, b, c)):
            raise ValueError("float64 required")
        if np.shares_memory(c, a) or np.shares_memory(c, b):
            raise ValueError("output must not alias an input")
        self.state = "RUNNING"
        n, tile = a.shape[0], self.tile
        try:
            for i in range(0, n, tile):
                for j in range(0, n, tile):
                    rows, cols = min(tile, n - i), min(tile, n - j)
                    acc = np.zeros((rows, cols), dtype=np.float64)
                    product = np.empty_like(acc)
                    for k in range(0, n, tile):
                        shared_a = a[i:i + tile, k:k + tile].copy()
                        shared_b = b[k:k + tile, j:j + tile].copy()
                        self.load_phases += 1
                        self.barriers += 1  # load complete before compute
                        np.matmul(shared_a, shared_b, out=product)
                        np.add(acc, product, out=acc)
                        self.barriers += 1  # compute complete before tile reuse
                    c[i:i + tile, j:j + tile] = acc
                    self.blocks += 1
                    self.active_lanes += rows * cols
                    self.masked_lanes += tile**2 - rows * cols
            self.launches += 1
        except BaseException:
            self.state = "FAULTED"
            raise
        self.state = "IDLE"

    def report(self):
        return {"backend": "CPU_NUMPY_TILED", "stream_count": 1,
                "block_scheduling": "serial_FIFO", "tile": self.tile,
                "launches": self.launches, "blocks": self.blocks,
                "shared_load_phases": self.load_phases,
                "modeled_barrier_events": self.barriers,
                "active_output_lanes": self.active_lanes,
                "masked_edge_lanes": self.masked_lanes,
                "cuda_compatible": False, "cycle_accurate": False, "gpu_used": False}


def cache_sweep(sizes, repeats):
    """Working-set sweep, not proof of cache residence/hit rate or full occupancy."""
    import numpy as np
    results = []
    for n in sizes:
        a, b, c = (np.empty((n, n), dtype=np.float64) for _ in range(3))
        # Analytic oracle: A[i,k]=r[i], B[k,j]=s[j], C[i,j]=n*r[i]*s[j].
        row = (np.arange(n) % 7 - 3).astype(np.float64)
        col = (np.arange(n) % 5 - 2).astype(np.float64)
        a[:] = row[:, None]
        b[:] = col[None, :]
        np.matmul(a, b, out=c)  # warmup is excluded from timing
        durations = []
        for _ in range(repeats):
            start = time.perf_counter()
            np.matmul(a, b, out=c)
            durations.append(time.perf_counter() - start)
        bad = sum(int(np.count_nonzero(c[i] != n * row[i] * col)) for i in range(n))
        if bad:
            raise RuntimeError(f"working-set sweep mismatch for n={n}: {bad}")
        elapsed = statistics.median(durations)
        results.append({"matrix_size": n, "matrix_working_set_bytes": 3 * n * n * 8,
                        "median_matmul_s": elapsed, "repeats": repeats,
                        "nominal_gflops_per_s": 2 * n**3 / elapsed / 1e9,
                        "mismatched_elements": bad, "cache_hits_measured": None})
        # Do not retain the old sweep during allocation of the next one.
        del a, b, c, row, col
    return results


def host_info():
    cpu = platform.processor() or None
    try:
        cpu = next(line.split(":", 1)[1].strip()
                   for line in Path("/proc/cpuinfo").read_text().splitlines()
                   if line.startswith("model name"))
    except (OSError, StopIteration):
        pass
    caches = []
    for path in sorted(Path("/sys/devices/system/cpu/cpu0/cache").glob("index*")):
        try:
            caches.append({key: (path / key).read_text().strip()
                           for key in ("level", "type", "size", "shared_cpu_list")})
        except OSError:
            pass
    return {"system": platform.system(), "architecture": platform.machine(),
            "cpu_reported_by_os": cpu, "python": platform.python_version(),
            "cpu0_cache_descriptions": caches,
            "target_board_identity_verified": False}


def execute(config):
    # Admission happens again in the child before importing/allocating NumPy.
    admission = budget_check(config, available_memory())
    import numpy as np
    start = time.perf_counter()
    words = config.memory_mib * MIB // 8
    bounds = shard_bounds(words, config.logical_shards)
    pool = np.empty(words, dtype=np.uint64)
    pattern_start = time.perf_counter()
    for invert in (False, True):
        patterns(pool, bounds, write=True, invert=invert)
        if patterns(pool, bounds, invert=invert):
            raise RuntimeError("address-pattern mismatch")
    pattern_s = time.perf_counter() - pattern_start
    refs = [fixtures(config.matrix_size, seed) for seed in range(7)]
    runtime = CpuBlockRuntime(config.tile)
    states = ["QUEUED"] * config.logical_shards
    n, cells = config.matrix_size, config.matrix_size**2
    kernel_s = 0.0
    for shard, (lo, hi) in enumerate(bounds):
        a, b, c = [pool[lo + slot * cells:lo + (slot + 1) * cells]
                   .view(np.float64).reshape(n, n) for slot in range(3)]
        expected_a, expected_b, expected_c = refs[shard % 7]
        a[:], b[:], c[:] = expected_a, expected_b, np.nan
        states[shard] = "RUNNING"
        for _ in range(config.rounds):
            begin = time.perf_counter()
            runtime.launch(a, b, c)
            kernel_s += time.perf_counter() - begin
            # Each launch is checked, not only the last round.
            if not np.array_equal(c, expected_c):
                states[shard] = "FAULTED"
                raise RuntimeError(f"matrix mismatch in logical shard {shard}")
        states[shard] = "VERIFIED"
    # Keep the pool live while changing working sets. Then recheck ALL its words:
    # A, B, C against fixtures and unused tails against the last address pattern.
    sweep = cache_sweep(config.cache_sizes, config.cache_repeats)
    matrix_runtime = runtime.report()
    rendering = {"status": "NOT_REQUESTED"}
    if config.render_path:
        from motionbricks.memory_lab_render import render_shards
        rendering = render_shards(config, runtime, pool, bounds, states)
    final_bad = 0
    for shard, (lo, hi) in enumerate(bounds):
        for slot, expected in enumerate(refs[shard % 7]):
            actual = pool[lo + slot * cells:lo + (slot + 1) * cells].view(np.float64)
            final_bad += int(np.count_nonzero(actual != expected.ravel()))
        final_bad += patterns(pool, [(lo + 3 * cells, hi)], invert=True)
    if final_bad:
        raise RuntimeError(f"final retained-data verification failed: {final_bad}")
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak *= 1 if sys.platform == "darwin" else 1024
    return {
        "status": "PASSED", "evidence_kind": "cpu_host_execution_logical_shards",
        "host": host_info(), "numpy_version": np.__version__, "child_admission": admission,
        "allocated_payload_bytes": pool.nbytes, "logical_shards_verified": len(states),
        "all_shards_verified": all(state == "VERIFIED" for state in states),
        "address_pattern_passes": 2, "pattern_write_and_check_s": pattern_s,
        "initial_words_checked": words * 2, "final_words_checked": words,
        "final_mismatched_words": final_bad, "matrix_kernel_total_s": kernel_s,
        "matrix_reference": "independent scalar Python integer dot products; exact equality",
        "payload_sha256": hashlib.sha256(memoryview(pool)).hexdigest(),
        "pseudo_gpu": runtime.report(), "matrix_runtime": matrix_runtime,
        "rendering": rendering, "working_set_sweep": sweep,
        "worker_peak_rss_bytes": peak, "elapsed_s": time.perf_counter() - start,
        "cache_hardware_counters_collected": False,
        "note": "OS-managed CPU RAM only; no physical DIMM routing, RDMA, CUDA or full-RAM certification",
    }


def main():
    try:
        payload = json.loads(sys.argv[1])
        payload["cache_sizes"] = tuple(payload["cache_sizes"])
        config = RunConfig(**payload)
        result = execute(config)
    except Exception as exc:
        print(json.dumps({"status": "FAILED", "error": type(exc).__name__, "detail": str(exc)}))
        return 1
    print(json.dumps(result, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
