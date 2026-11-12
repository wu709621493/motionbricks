"""Independent numerical identities, failure cases and CLI reproducibility."""
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from motionbricks.rb14_feasibility import (
    Mode, Noise, RB87_MASS_KG, comparison, covariance_inner,
    geometry_budget, local_resolution, modes_for, noise_budget, response, shifts_from_weights,
)

ROOT = Path(__file__).resolve().parents[2]


class PhysicsTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "configs/rb14_phase1.json").read_text())
        self.modes = modes_for(self.config["device"])
        self.noise = Noise("test", 0.05, 0.01, 0.001, 1e-10)

    def test_known_atomic_mass_and_reference_shift(self):
        self.assertAlmostEqual(RB87_MASS_KG / 1e-25, 1.4431609, places=6)
        one = shifts_from_weights(1e8, 1e-17, [.5])
        fourteen = shifts_from_weights(1e8, 1e-17, [.5] * 14)
        self.assertAlmostEqual(one["linear_shift_hz"], -.36079023, places=7)
        self.assertAlmostEqual(fourteen["linear_shift_hz"], -5.0510633, places=6)
        self.assertAlmostEqual(fourteen["linear_shift_hz"], 14 * one["linear_shift_hz"])
        self.assertLess(abs(fourteen["linearization_error_hz"]), 4e-7)
        self.assertEqual(shifts_from_weights(1e8, 1e-17, [])["linear_shift_hz"], 0)

    def test_fixed_mass_eigenvalue_identity(self):
        # Algebraic ratio derived independently from f = sqrt(K/M)/(2*pi).
        ratio = 1e-4
        mass = RB87_MASS_KG / ratio
        result = shifts_from_weights(1e8, mass, [1])
        expected = 1e8 * (1 / math.sqrt(1 + ratio) - 1)
        self.assertAlmostEqual(result["frozen_mode_shift_hz"], expected, places=7)
        self.assertLess(abs(result["frozen_mode_shift_hz"]), abs(result["linear_shift_hz"]))

    def test_scaling_and_peak_node(self):
        baseline = shifts_from_weights(1e8, 1e-17, [.5])["linear_shift_hz"]
        self.assertEqual(shifts_from_weights(2e8, 1e-17, [.5])["linear_shift_hz"], 2 * baseline)
        self.assertEqual(shifts_from_weights(1e8, 2e-17, [.5])["linear_shift_hz"], baseline / 2)
        m = self.modes[0]
        self.assertAlmostEqual(m.weight((m.lx_m / 2, m.ly_m / 2)), 1)
        self.assertEqual(m.weight((0, m.ly_m / 2)), 0)

    def test_peak_normalized_modal_mass(self):
        m = self.modes[0]
        n = 80
        average = math.fsum(m.weight(((i + .5) * m.lx_m / n, (j + .5) * m.ly_m / n))
                            for i in range(n) for j in range(n)) / n ** 2
        self.assertAlmostEqual(average, .25, places=13)

    def test_gradient_against_central_difference(self):
        pos = (61e-9, 89e-9)
        step = 1e-12
        for mode in self.modes:
            for axis in (0, 1):
                a, b = list(pos), list(pos)
                a[axis] += step; b[axis] -= step
                numerical = (mode.weight(a) - mode.weight(b)) / (2 * step)
                self.assertAlmostEqual(numerical / mode.gradient(pos)[axis], 1, places=8)

    def test_multimode_breaks_swap_but_not_reflection(self):
        a, swap, mirror = [(60e-9, 90e-9)], [(90e-9, 60e-9)], [(240e-9, 90e-9)]
        av, bv, cv = [response(self.modes, p) for p in (a, swap, mirror)]
        self.assertAlmostEqual(av[0], bv[0], places=12)
        self.assertGreater(max(abs(x - y) for x, y in zip(av, bv)), .1)
        for x, y in zip(av, cv):
            self.assertAlmostEqual(x, y, places=12)
        self.assertNotEqual(self.modes[1].frequency_hz, self.modes[2].frequency_hz)

    def test_single_mode_cannot_locate_two_coordinates(self):
        pos = (60e-9, 90e-9)
        one = local_resolution(self.modes[:1], pos, self.noise, 10)
        multi = local_resolution(self.modes, pos, self.noise, 10)
        self.assertEqual(one["fisher_rank"], 1)
        self.assertIsNone(one["local_sigma_x_nm"])
        self.assertEqual(multi["fisher_rank"], 2)
        self.assertGreater(multi["local_sigma_x_nm"], 0)
        center = local_resolution(self.modes, (150e-9, 150e-9), self.noise, 10)
        self.assertLess(center["fisher_rank"], 2)

    def test_rejects_invalid_physical_inputs(self):
        for mass in (0, -1, float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                shifts_from_weights(1e8, mass, [.5])
        for w in (-.1, 1.01, float("nan")):
            with self.assertRaises(ValueError):
                shifts_from_weights(1e8, 1e-17, [w])
        with self.assertRaises(ValueError):
            shifts_from_weights(1e8, 1e-25, [1])
        with self.assertRaises(ValueError):
            self.modes[0].weight((301e-9, 0))

    def test_geometry_incompatibility_and_scaling(self):
        a = geometry_budget(300e-9, 20e-9, 2330, 160e9, .22, 1e8, 1.3)
        b = geometry_budget(600e-9, 20e-9, 2330, 160e9, .22, 1e8, 1.3)
        self.assertAlmostEqual(a["effective_mass_kg"] / 1e-18, 1.0485)
        self.assertGreater(a["bending_only_f11_hz"], 1e9)
        self.assertFalse(a["target_allows_nonnegative_tension"])
        self.assertIsNone(a["required_sigma_x_pa"])
        self.assertAlmostEqual(a["bending_only_f11_hz"], 4 * b["bending_only_f11_hz"])


class NoiseTests(unittest.TestCase):
    setUp = PhysicsTests.setUp
    def test_reference_difference_noise_and_drift(self):
        profile = Noise("white", 2, 0, 0, 0)
        result = noise_budget(5, self.modes[0], profile, 8, 0, 5)
        self.assertAlmostEqual(result["sigma_difference_hz"], 1)
        self.assertTrue(result["passes_margin"])
        profile = Noise("drift", 2, 0, .5, 0)
        result = noise_budget(5, self.modes[0], profile, 8, 2, 5)
        self.assertEqual(result["drift_bound_hz"], 5)
        self.assertFalse(result["passes_margin"])
        self.assertIsNone(result["allowed_white_hz_sqrt_s"])

    def test_threshold_inverse_is_consistent(self):
        profile = Noise("budget", 0.1, .02, .001, 1e-10)
        result = noise_budget(.5, self.modes[0], profile, 10, 0, 5)
        boundary = Noise("boundary", result["allowed_white_hz_sqrt_s"], .02, .001, 1e-10)
        check = noise_budget(.5, self.modes[0], boundary, 10, 0, 5)
        self.assertAlmostEqual(check["required_signal_hz"], .5, places=13)

    def test_common_noise_does_not_average_as_independent(self):
        m = self.modes[0]
        equal = [m, m]
        independent = Noise("independent", 1, 0, 0, 0)
        common = Noise("common", 1, 0, 0, 1e-7)
        one = covariance_inner([1], [1], [m], common, 1)
        two = covariance_inner([1, 1], [1, 1], equal, common, 1)
        self.assertLess(two / one, 1.02)
        self.assertAlmostEqual(covariance_inner([1, 1], [1, 1], equal, independent, 1), 1)
        # Antisymmetric response rejects common noise in this two-channel toy case.
        self.assertAlmostEqual(covariance_inner([1, -1], [1, -1], equal, common, 1), 1)

    def test_longer_averaging_can_fail(self):
        a = noise_budget(.36, self.modes[0], self.noise, 10, 0, 5)
        b = noise_budget(.36, self.modes[0], self.noise, 1000, 0, 5)
        self.assertTrue(a["passes_margin"])
        self.assertFalse(b["passes_margin"])

    def test_zero_distance_never_passes(self):
        result = comparison([0, 0, 0], self.modes, self.noise, 10, 0, 5)
        self.assertFalse(result["passes_margin"])
        self.assertEqual(result["drift_robust_lower_bound"], 0)


class CliTests(unittest.TestCase):
    def test_repeatable_cli_and_status_boundaries(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp) / "a", Path(temp) / "b"
            for target in (a, b):
                result = subprocess.run([sys.executable, "-S", "-m", "motionbricks.rb14_feasibility",
                                         "--out-dir", str(target)], cwd=ROOT, capture_output=True,
                                        text=True, timeout=20, check=True)
                self.assertEqual(json.loads(result.stdout)["scan_rows"], 144)
            self.assertEqual(sorted(p.name for p in a.iterdir()), sorted(p.name for p in b.iterdir()))
            for path in a.iterdir():
                self.assertEqual(path.read_bytes(), (b / path.name).read_bytes())
            report = json.loads((a / "report.json").read_text())
            self.assertEqual(report["evidence_origin"], "SIMULATED")
            self.assertEqual(report["concept_status"], "CONCEPT_ONLY")
            self.assertEqual(set(report["hardware_status"].values()), {"NOT_RUN"})
            self.assertIsNone(report["entropy_bits"])
            grid = report["grid_pair_comparison"]
            self.assertGreater(grid[0]["exact_collisions_at_1e-10_hz"], grid[1]["exact_collisions_at_1e-10_hz"])
            self.assertGreater(grid[1]["exact_collisions_at_1e-10_hz"], 0)


if __name__ == "__main__":
    unittest.main()
