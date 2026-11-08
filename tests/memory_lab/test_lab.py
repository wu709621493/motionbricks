"""Physical limits, independent numerical checks, corruption and process refusal."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np

from motionbricks.memory_lab import (MIB, RunConfig, budget_check, build_plan,
                                     cgroup_headrooms, run, shard_bounds, supervise)
from motionbricks.memory_lab_worker import CpuBlockRuntime, cache_sweep, fixtures, patterns
from motionbricks.prebios_power import synthetic_trace


class PlanningTests(unittest.TestCase):
    def test_physical_1000_requires_125_boards(self):
        plan = build_plan()
        self.assertEqual(plan["minimum_nodes_by_slots_and_capacity"], 125)
        self.assertFalse(plan["single_board_can_fit"])
        self.assertFalse(plan["purchase_completed"])
        self.assertFalse(plan["distributed_backend_implemented"])
        self.assertEqual(plan["channels_per_cpu"], 4)
        self.assertEqual(plan["raw_capacity_tib"], 15.625)

    def test_cpu_capacity_limit_overrides_slot_count(self):
        self.assertEqual(build_plan(1000, 32)["minimum_nodes_by_slots_and_capacity"], 250)
        self.assertTrue(build_plan(8, 16)["single_board_can_fit"])
        self.assertFalse(build_plan(8, 32)["single_board_can_fit"])

    def test_ranges_and_nonfinite_values(self):
        for fields in ({"logical_shards": True}, {"memory_mib": 0}, {"threads": 0},
                       {"timeout_s": float("nan")}, {"timeout_s": float("inf")},
                       {"tile": 33}, {"cache_sizes": (2049,)}, {"cache_sizes": ()},
                       {"matrix_size": 128, "memory_mib": 1}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                RunConfig(**fields)

    def test_shard_partition_has_no_gaps_or_overlap(self):
        parts = shard_bounds(10007, 1000)
        self.assertEqual(parts[0][0], 0)
        self.assertEqual(parts[-1][1], 10007)
        self.assertEqual(sum(hi - lo for lo, hi in parts), 10007)
        self.assertTrue(all(a[1] == b[0] for a, b in zip(parts, parts[1:])))
        self.assertLessEqual(max(hi - lo for lo, hi in parts) - min(hi - lo for lo, hi in parts), 1)

    def test_available_memory_refusal(self):
        for available in (None, 0, 128 * MIB):
            with self.subTest(available=available), self.assertRaises(ValueError):
                budget_check(RunConfig(), {"available_bytes": available})
        accepted = budget_check(RunConfig(), {"available_bytes": 4 * 1024 * MIB})
        self.assertGreater(accepted["admission_limit_bytes"], accepted["estimated_worker_bytes"])

    def test_finite_parent_cgroup_limit_and_high(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = root / "child"
            child.mkdir()
            for path, limit, current in ((root, "1000", "900"), (child, "max", "50")):
                (path / "memory.max").write_text(limit)
                (path / "memory.current").write_text(current)
                (path / "memory.high").write_text("max")
            (child / "memory.high").write_text("200")
            self.assertEqual(sorted(cgroup_headrooms(root, "/child")), [100, 150])
            self.assertEqual(cgroup_headrooms(root, "../../escape"), [])


class NumericalTests(unittest.TestCase):
    def test_tiled_outputs_match_independent_oracle_with_edge_lanes(self):
        for n, tile in ((1, 1), (5, 3), (17, 8), (32, 16)):
            for seed in (0, 3, 6):
                with self.subTest(n=n, tile=tile, seed=seed):
                    a, b, expected = fixtures(n, seed)
                    c = np.full_like(a, np.nan)
                    runtime = CpuBlockRuntime(tile)
                    runtime.launch(a, b, c)
                    np.testing.assert_array_equal(c, expected)
                    self.assertEqual(runtime.active_lanes, n * n)
                    self.assertEqual(runtime.barriers, runtime.load_phases * 2)
                    self.assertEqual(runtime.state, "IDLE")
                    if n % tile:
                        self.assertGreater(runtime.masked_lanes, 0)

    def test_output_alias_is_refused(self):
        a, b, _ = fixtures(4, 0)
        with self.assertRaises(ValueError):
            CpuBlockRuntime(2).launch(a, b, a)

    def test_invalid_tile_refused(self):
        for tile in (0, -1, True, 33):
            with self.assertRaises(ValueError):
                CpuBlockRuntime(tile)

    def test_kernel_fault_stays_faulted(self):
        a, b, c = fixtures(4, 0)
        runtime = CpuBlockRuntime(2)
        with patch.object(np, "matmul", side_effect=RuntimeError("test fault")):
            with self.assertRaises(RuntimeError):
                runtime.launch(a, b, c)
        self.assertEqual(runtime.state, "FAULTED")
        with self.assertRaises(RuntimeError):
            runtime.launch(a, b, c)

    def test_address_patterns_detect_bit_flip_and_swapped_shards(self):
        pool = np.empty(10007, dtype=np.uint64)
        bounds = shard_bounds(len(pool), 1000)
        for invert in (False, True):
            patterns(pool, bounds, write=True, invert=invert)
            self.assertEqual(patterns(pool, bounds, invert=invert), 0)
            pool[-1] ^= np.uint64(1)
            self.assertEqual(patterns(pool, bounds, invert=invert), 1)
        patterns(pool, bounds, write=True)
        pool[:10], pool[10:20] = pool[10:20].copy(), pool[:10].copy()
        self.assertEqual(patterns(pool, bounds), 20)

    def test_cache_sweep_analytic_result_and_no_cache_claim(self):
        result = cache_sweep((7, 33), 2)
        self.assertEqual(result[1]["matrix_working_set_bytes"], 3 * 33**2 * 8)
        for row in result:
            self.assertEqual(row["mismatched_elements"], 0)
            self.assertIsNone(row["cache_hits_measured"])


@unittest.skipUnless(os.name == "posix", "POSIX supervisor")
class ProcessTests(unittest.TestCase):
    def test_worker_timeout_is_bounded_and_reaped(self):
        begin = time.monotonic()
        result = supervise([sys.executable, "-c", "import time; time.sleep(20)"], timeout_s=.1)
        self.assertEqual(result["status"], "TIMEOUT")
        self.assertTrue(result["worker_reaped"])
        self.assertLess(time.monotonic() - begin, 5)

    def test_worker_nonzero_exit_and_invalid_protocol(self):
        for code, status in (("raise SystemExit(7)", "WORKER_FAILED"),
                             ("print('not json')", "WORKER_PROTOCOL_ERROR"),
                             ("print('{}')", "WORKER_PROTOCOL_ERROR")):
            result = supervise([sys.executable, "-c", code], timeout_s=5)
            self.assertEqual(result["status"], status)

    def test_power_fault_prevents_worker_start(self):
        payload = synthetic_trace()
        payload["observations"][0]["frame"]["rails"][0]["current_a"] = 100
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.json"
            path.write_text(json.dumps(payload))
            with patch("motionbricks.memory_lab.supervise", side_effect=AssertionError("must not start")):
                result = run(RunConfig(), path)
            self.assertEqual(result["status"], "POWER_TRACE_REFUSED")
            self.assertFalse(result["worker_started"])

    def test_full_1000_shard_cpu_run(self):
        config = RunConfig(memory_mib=1, matrix_size=4, tile=3,
                           cache_sizes=(16, 32), cache_repeats=1, timeout_s=30)
        result = run(config)
        self.assertEqual(result["status"], "PASSED", result)
        self.assertEqual(result["logical_shards_verified"], 1000)
        self.assertEqual(result["pseudo_gpu"]["launches"], 1000)
        self.assertEqual(result["final_words_checked"] * 8, MIB)
        self.assertEqual(result["initial_words_checked"] * 8, 2 * MIB)
        self.assertEqual(result["final_mismatched_words"], 0)
        for flag in ("gpu_used", "all_ram_tested", "target_board_tested", "all_cache_used_proven"):
            self.assertFalse(result[flag])
        self.assertIsNone(result["physical_dimm_count_verified"])

    def test_cli_invalid_budget_has_nonzero_exit(self):
        process = subprocess.run([sys.executable, "-m", "motionbricks.memory_lab", "run",
                                  "--memory-mib", "0"], capture_output=True, text=True, timeout=5)
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(json.loads(process.stdout)["status"], "REFUSED")


if __name__ == "__main__":
    unittest.main()
