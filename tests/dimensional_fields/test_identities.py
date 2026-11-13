"""Independent analytic limits, convergence and machine-readable failure."""
import json
import math
from pathlib import Path
import subprocess
import sys
import unittest

from tools.research.check_dimensional_identities import report, scalar_benchmark, wall_state

ROOT = Path(__file__).resolve().parents[2]


class IdentityTests(unittest.TestCase):
    def test_rk4_converges_toward_analytic_solution(self):
        coarse, fine = scalar_benchmark(64), scalar_benchmark(128)
        self.assertGreater(coarse["max_position_error"] / fine["max_position_error"], 14)
        self.assertLess(coarse["max_position_error"] / fine["max_position_error"], 18)

    def test_wall_minkowski_hyperbola(self):
        for tau in (0, .5, 1, 8):
            w = wall_state(tau)
            self.assertAlmostEqual(w["rho"] ** 2 - tau ** 2, 1, places=12)
            self.assertAlmostEqual(w["gamma"], 1 / math.sqrt(1 - w["beta"] ** 2), places=11)
        self.assertAlmostEqual(wall_state(1)["beta"], 1 / math.sqrt(2))

    def test_validated_domain(self):
        for value in (True, float("nan"), float("inf"), 101):
            with self.subTest(value=value), self.assertRaises(ValueError):
                wall_state(value)
        for value in (True, 31, 20001, 32.0):
            with self.subTest(value=value), self.assertRaises(ValueError):
                scalar_benchmark(value)

    def test_default_accuracy_and_unperformed_work(self):
        r = report()
        self.assertEqual(r["verdict"], "PASS")
        for key in ("full_coupled_field_solver", "dimension_change", "experimental_fit"):
            self.assertEqual(r[key], "NOT_RUN")

    def test_coarse_run_is_a_failure_not_a_pass(self):
        self.assertEqual(report(32)["verdict"], "FAIL")

    def test_cli_preserves_failure_exit_code(self):
        command = [sys.executable, "-S", "tools/research/check_dimensional_identities.py"]
        for extra, code, verdict in (([], 0, "PASS"), (["--steps", "32"], 1, "FAIL")):
            p = subprocess.run(command + extra, cwd=ROOT, capture_output=True, text=True, timeout=10)
            self.assertEqual(p.returncode, code, p.stderr)
            self.assertEqual(json.loads(p.stdout)["verdict"], verdict)


if __name__ == "__main__":
    unittest.main()
