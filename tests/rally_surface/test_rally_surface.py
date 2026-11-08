"""Analytic controls, counterexamples, provenance and reproducibility checks."""
import copy
from dataclasses import replace
import json
import math
from pathlib import Path
import subprocess
import sys
import unittest

from motionbricks.rally_surface import (
    EVIDENCE, G, Scenario, Segment, Soil, Surface, evaluate, make_route, run_study, summarize,
)

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "docs/examples/rally_surface_synthetic.json"


class SurfaceTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(CONFIG.read_text(encoding="utf-8"))
        self.soil = Soil(**self.config["soil"])
        self.surfaces = {s["name"]: Surface(**s) for s in self.config["surfaces"]}
        self.segment = Segment(100, 0, 50, 6)
        self.case = Scenario(1400, 8, 0, .8, 30, 0, 0)

    def evaluate(self, name="bare_mud", **changes):
        return evaluate(self.segment, self.soil, self.surfaces[name],
                        replace(self.case, **changes))

    def test_flat_circle_analytic_demand(self):
        surface = replace(self.surfaces["asphalt"], rolling_coefficient=0)
        value = evaluate(self.segment, self.soil, surface, self.case)
        self.assertAlmostEqual(value["demand_n"], 1400 * 8**2 / 50)
        self.assertAlmostEqual(value["capacity_n"], value["effective_mu"] * 1400 * G)

    def test_combined_forces_not_independent_limits(self):
        surface = replace(self.surfaces["asphalt"], rolling_coefficient=0)
        value = evaluate(self.segment, self.soil, surface,
                         replace(self.case, acceleration_m_s2=2))
        self.assertAlmostEqual(value["demand_n"], math.hypot(2800, 1792))

    def test_signed_grade_and_braking(self):
        surface = replace(self.surfaces["asphalt"], rolling_coefficient=0)
        results = [evaluate(Segment(100, grade, None, 6), self.soil, surface,
                            replace(self.case, acceleration_m_s2=0)) for grade in (.1, -.1)]
        expected = self.case.mass_kg * G * math.sin(math.atan(.1))
        for value in results:
            self.assertAlmostEqual(value["demand_n"], expected)

    def test_cohesionless_ground_limit(self):
        soil = replace(self.soil, cohesion_dry_pa=0, cohesion_wet_pa=0,
                       phi_dry_deg=10, phi_wet_deg=10)
        value = evaluate(self.segment, soil, self.surfaces["asphalt"], self.case)
        self.assertAlmostEqual(value["effective_mu"], math.tan(math.radians(10)))
        self.assertIn("ground_shear", value["limiting_interfaces"])

    def test_loose_sheet_can_be_worse_than_mud(self):
        self.assertLess(self.evaluate("loose_sack")["effective_mu"],
                        self.evaluate("bare_mud")["effective_mu"])

    def test_anchor_cannot_bypass_weak_ground(self):
        soil = replace(self.soil, cohesion_dry_pa=0, cohesion_wet_pa=0,
                       phi_dry_deg=5, phi_wet_deg=5)
        surface = replace(self.surfaces["anchored_mat"], anchor_capacity_n=1e7)
        value = evaluate(self.segment, soil, surface, self.case)
        self.assertAlmostEqual(value["effective_mu"], math.tan(math.radians(5)))

    def test_zero_strength_sheet_has_zero_capacity(self):
        surface = replace(self.surfaces["anchored_mat"], sheet_capacity_n=0)
        self.assertEqual(evaluate(self.segment, self.soil, surface, self.case)["capacity_n"], 0)

    def test_bearing_failure_separate_from_traction(self):
        value = evaluate(Segment(100, 0, None, 6), self.soil,
                         self.surfaces["bare_mud"], replace(self.case, saturation=1))
        self.assertTrue(value["bearing_exceeded"])
        self.assertFalse(value["demand_exceeded"])

    def test_water_balance_and_protected_routing(self):
        for routing in (0, .9, 1):
            value = self.evaluate("asphalt", protected_routing_fraction=routing)
            self.assertAlmostEqual(value["rainfall_m3"], 18)
            self.assertAlmostEqual(value["runoff_m3"], 17.1)
            self.assertAlmostEqual(value["runoff_m3"],
                                   value["protected_runoff_m3"] + value["unprotected_runoff_m3"])
            self.assertAlmostEqual(value["rainfall_m3"],
                                   value["runoff_m3"] + value["non_runoff_m3"])
        a = self.evaluate("asphalt")
        b = self.evaluate("asphalt", protected_routing_fraction=.9)
        self.assertEqual(a["road_detachment_index"], b["road_detachment_index"])
        self.assertAlmostEqual(b["downslope_exposure_index"], a["downslope_exposure_index"] / 10)

    def test_paving_does_not_guarantee_less_downslope_exposure(self):
        mud, asphalt = self.evaluate(), self.evaluate("asphalt")
        self.assertLess(asphalt["road_detachment_index"], mud["road_detachment_index"])
        self.assertGreater(asphalt["downslope_exposure_index"], mud["downslope_exposure_index"])

    def test_no_rain_no_rain_driven_erosion(self):
        value = self.evaluate(rain_mm=0, previous_passes=100)
        for key in ("runoff_m3", "road_detachment_index", "downslope_exposure_index"):
            self.assertEqual(value[key], 0)

    def test_wear_reduces_capacity_and_exposes_surface(self):
        new = self.evaluate("anchored_mat")
        worn = self.evaluate("anchored_mat", previous_passes=100)
        self.assertLess(worn["effective_mu"], new["effective_mu"])
        self.assertGreater(worn["road_detachment_index"], new["road_detachment_index"])

    def test_reinforcement_has_matched_initial_control(self):
        a, b = self.evaluate("gravel_control"), self.evaluate("buried_geotextile_gravel")
        self.assertEqual(a, b)
        a = self.evaluate("gravel_control", previous_passes=100)
        b = self.evaluate("buried_geotextile_gravel", previous_passes=100)
        self.assertGreater(b["effective_mu"], a["effective_mu"])

    def test_route_scale_corner_count_and_provenance(self):
        for spec in self.config["routes"]:
            route = make_route(spec)
            self.assertAlmostEqual(math.fsum(s.length_m for s in route), spec["length_m"])
            self.assertEqual(sum(s.radius_m is not None for s in route), spec["corners"])
        bad = dict(self.config["routes"][0], geometry_evidence="SURVEYED")
        with self.assertRaises(ValueError):
            make_route(bad)

    def test_segment_subdivision_invariance(self):
        a = summarize([self.segment], self.soil, self.surfaces["asphalt"], self.case)
        b = summarize([replace(self.segment, length_m=25)] * 4,
                      self.soil, self.surfaces["asphalt"], self.case)
        self.assertEqual(a, b)

    def test_exceedance_is_length_weighted(self):
        route = [Segment(90, 0, None, 6), Segment(10, 0, 1, 6)]
        result = summarize(route, self.soil, self.surfaces["asphalt"], self.case)
        self.assertEqual(result["demand_exceeded_length_fraction"], .1)

    def test_invalid_inputs(self):
        for value in (float("nan"), float("inf"), -1, True, "30"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                replace(self.case, rain_mm=value)
        for value in (0, -3, float("nan")):
            with self.assertRaises(ValueError):
                replace(self.segment, radius_m=value)
        for value in (1.5, True, -1):
            with self.assertRaises(ValueError):
                replace(self.case, previous_passes=value)
        with self.assertRaises(ValueError):
            replace(self.surfaces["loose_sack"], interface_mu_wet=None)
        with self.assertRaises(ValueError):
            replace(self.case, saturation=1.1)
        with self.assertRaises(ValueError):
            summarize([], self.soil, self.surfaces["asphalt"], self.case)

    def test_study_serializable_deterministic_and_inputs_retained(self):
        config = copy.deepcopy(self.config)
        config["routes"][0]["corners"] = 2
        config["routes"][1]["corners"] = 2
        a, b = run_study(config), run_study(config)
        self.assertEqual(a, b)
        self.assertEqual(a["inputs"], config)
        self.assertEqual(a["evidence"], EVIDENCE)
        self.assertEqual(len(a["cases"]), 216)
        self.assertEqual(len(a["model_sha256"]), 64)
        json.dumps(a, allow_nan=False)

    def test_bad_schema_empty_matrix_and_duplicate_ids(self):
        for key, value in (("schema_version", 2), ("parameter_evidence", "MEASURED"),
                           ("routes", []), ("passes", [])):
            bad = dict(self.config, **{key: value})
            with self.assertRaises(ValueError):
                run_study(bad)
        bad = dict(self.config, surfaces=self.config["surfaces"] * 2)
        with self.assertRaises(ValueError):
            run_study(bad)

    def test_cli_rejects_bad_config_without_traceback(self):
        result = subprocess.run([sys.executable, "-S", "-m", "motionbricks.rally_surface",
                                 "--config", str(ROOT / "missing-study.json")],
                                cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid study", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
