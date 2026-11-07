import copy
from dataclasses import replace
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from motionbricks.prebios_power import (
    PowerGuard, compare_supply_paths, dc_power_w, frame_from_dict,
    profile_from_dict, resistive_loss_w, review_trace, synthetic_trace,
)


class PowerTests(unittest.TestCase):
    def setUp(self):
        self.payload = synthetic_trace()
        self.profile = profile_from_dict(self.payload["profile"])
        self.frame = frame_from_dict(self.payload["observations"][0]["frame"])
        self.guard = PowerGuard(self.profile)

    def change_rail(self, rail_id="VDD", **changes):
        return replace(self.frame, rails=tuple(
            replace(r, **changes) if r.rail_id == rail_id else r for r in self.frame.rails))

    def test_si_power_and_loss(self):
        self.assertEqual(dc_power_w(1.25, 2), 2.5)
        self.assertEqual(resistive_loss_w(2, 0.05), 0.2)
        self.assertEqual(dc_power_w(1.25, 0), 0)

    def test_supply_comparison_accounts_for_conversion_loss(self):
        rows = compare_supply_paths(load_power_w=9, bus_voltages_v=[5, 10],
                                    path_resistance_ohm=0.1, converter_efficiency=0.9)
        self.assertEqual(rows[0]["input_current_a"], 2)
        self.assertEqual(rows[1]["input_current_a"], 1)
        self.assertAlmostEqual(rows[0]["wire_loss_w"], 4 * rows[1]["wire_loss_w"])
        self.assertEqual(rows[0]["conversion_loss_w"], 1)
        self.assertAlmostEqual(rows[0]["source_power_w"], 10.4)
        self.assertAlmostEqual(rows[0]["source_terminal_v"] * rows[0]["input_current_a"], 10.4)

    def test_bad_supply_inputs(self):
        kwargs = dict(load_power_w=9, bus_voltages_v=[5],
                      path_resistance_ohm=0.1, converter_efficiency=0.9)
        for change in ({"converter_efficiency": 0}, {"converter_efficiency": 1.1},
                       {"bus_voltages_v": [0]}, {"bus_voltages_v": []},
                       {"path_resistance_ohm": -1}, {"load_power_w": True}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                compare_supply_paths(**(kwargs | change))

    def test_invalid_scalar_and_overflow(self):
        for value in (True, "1.2", None, math.nan, math.inf, -1, 10**400):
            with self.subTest(value=repr(value)[:30]), self.assertRaises(ValueError):
                dc_power_w(value, 2)
        with self.assertRaises(ValueError):
            dc_power_w(1e308, 1e308)

    def test_input_and_load_are_not_added_together(self):
        report = self.guard.observe(self.frame, now_s=0)
        self.assertEqual(report["status"], "WITHIN_DECLARED_ENVELOPE")
        self.assertAlmostEqual(report["metrics"]["total_load_dc_power_w"], 4.53)
        self.assertAlmostEqual(report["metrics"]["total_input_dc_power_w"], 5.5)
        self.assertFalse(report["hardware_authorized"])
        self.assertFalse(report["memory_stability_validated"])
        self.assertFalse(report["lifetime_proven"])

    def test_unknown_resistance_is_not_zero(self):
        report = self.guard.observe(self.frame, now_s=0)
        self.assertIsNone(report["metrics"]["rails"]["VDDQ"]["modeled_dc_wire_loss_w"])
        self.assertAlmostEqual(report["metrics"]["rails"]["VDD"]["modeled_dc_wire_loss_w"], 0.02)

    def test_no_input_measurement_is_unknown(self):
        profile = replace(self.profile, rails=tuple(r for r in self.profile.rails if r.accounting == "load"))
        frame = replace(self.frame, rails=tuple(r for r in self.frame.rails if r.rail_id != "VIN"))
        report = PowerGuard(profile).observe(frame, now_s=0)
        self.assertIsNone(report["metrics"]["total_input_dc_power_w"])

    def test_voltage_and_uncertainty_limits(self):
        for voltage, error in ((1.51, 0), (1.39, 0), (1.49, 0.02), (1.41, 0.02)):
            with self.subTest(voltage=voltage, error=error):
                report = PowerGuard(self.profile).observe(
                    self.change_rail(voltage_v=voltage, voltage_error_v=error), now_s=0)
                self.assertIn("VDD:VOLTAGE_LIMIT", report["reasons"])

    def test_current_and_uncertainty_limits(self):
        for current, error in ((4.1, 0), (3.99, 0.02)):
            report = PowerGuard(self.profile).observe(
                self.change_rail(current_a=current, current_error_a=error), now_s=0)
            self.assertIn("VDD:CURRENT_LIMIT", report["reasons"])

    def test_power_limit_can_trip_before_current_limit(self):
        report = self.guard.observe(self.change_rail(current_a=3.5, current_error_a=0), now_s=0)
        self.assertIn("VDD:POWER_LIMIT", report["reasons"])
        self.assertNotIn("VDD:CURRENT_LIMIT", report["reasons"])

    def test_aggregate_power_uses_uncertainty_upper_bound(self):
        # Nominal 4.53 W fits; the uncertainty bound is 4.59925 W.
        profile = replace(self.profile, max_total_load_power_w=4.58)
        report = PowerGuard(profile).observe(self.frame, now_s=0)
        self.assertEqual(report["reasons"], ["TOTAL_LOAD_POWER_LIMIT"])

    def test_temperature_cutoff_is_exclusive(self):
        for temp, error in ((70, 0), (69, 1), (-1, 0)):
            report = PowerGuard(self.profile).observe(
                self.change_rail(temp_c=temp, temp_error_c=error), now_s=0)
            self.assertIn("VDD:TEMPERATURE_LIMIT", report["reasons"])

    def test_invalid_sensor_values_fail_closed(self):
        for field, value in (("voltage_v", math.nan), ("current_a", -0.1),
                             ("current_a", True), ("temp_c", None),
                             ("voltage_error_v", -1), ("current_error_a", math.inf),
                             ("temp_error_c", "1"), ("voltage_v", 1e308)):
            with self.subTest(field=field, value=value):
                report = PowerGuard(self.profile).observe(self.change_rail(**{field: value}), now_s=0)
                self.assertEqual(report["status"], "TRIPPED")
                self.assertIsNone(report["metrics"])

    def test_missing_extra_and_duplicate_rails(self):
        for rails in (self.frame.rails[:-1], self.frame.rails + (self.frame.rails[0],),
                      self.frame.rails + (replace(self.frame.rails[0], rail_id="UNKNOWN"),)):
            report = PowerGuard(self.profile).observe(replace(self.frame, rails=rails), now_s=0)
            self.assertEqual(report["reasons"], ["MISSING_EXTRA_OR_DUPLICATE_RAIL"])

    def test_profile_identity_mismatches(self):
        for change in ({"platform_id": "other"}, {"profile_id": "other"},
                       {"generation": "DDR4"}, {"rate_mts": 6400}):
            report = PowerGuard(self.profile).observe(replace(self.frame, **change), now_s=0)
            self.assertEqual(report["reasons"], ["PLATFORM_OR_PROFILE_MISMATCH"])

    def test_ddr4_has_separate_declared_profile(self):
        profile = replace(self.profile, generation="DDR4", rate_mts=3200)
        frame = replace(self.frame, generation="DDR4", rate_mts=3200)
        self.assertEqual(PowerGuard(profile).observe(frame, now_s=0)["status"], "WITHIN_DECLARED_ENVELOPE")
        self.assertEqual(PowerGuard(profile).observe(self.frame, now_s=0)["status"], "TRIPPED")

    def test_stale_future_and_invalid_time(self):
        for now in (0.2, -1, True, math.nan):
            self.assertEqual(PowerGuard(self.profile).observe(self.frame, now_s=now)["status"], "TRIPPED")
        self.assertEqual(PowerGuard(self.profile).observe(replace(self.frame, timestamp_s=1), now_s=0)["status"], "TRIPPED")

    def test_duplicate_reverse_and_gap_samples(self):
        for timestamp in (0.5, 0.4, 1.6):
            guard = PowerGuard(self.profile)
            guard.observe(replace(self.frame, timestamp_s=0.5), now_s=0.5)
            report = guard.observe(replace(self.frame, timestamp_s=timestamp), now_s=timestamp)
            self.assertEqual(report["reasons"], ["SAMPLE_CLOCK_OR_GAP"])

    def test_observer_clock_also_must_advance(self):
        self.guard.observe(self.frame, now_s=0.05)
        report = self.guard.observe(replace(self.frame, timestamp_s=0.01), now_s=0.05)
        self.assertEqual(report["reasons"], ["OBSERVER_CLOCK_OR_GAP"])

    def test_boot_change_trips(self):
        self.guard.observe(self.frame, now_s=0)
        report = self.guard.observe(replace(self.frame, timestamp_s=0.5, boot_id="second"), now_s=0.5)
        self.assertEqual(report["reasons"], ["BOOT_CHANGED"])

    def test_trip_cannot_be_erased_by_healthy_sample(self):
        fault = self.guard.observe(self.change_rail(current_a=100), now_s=0)
        self.assertEqual(self.guard.observe(replace(self.frame, timestamp_s=0.5), now_s=0.5), fault)

    def test_malformed_objects_trip(self):
        for frame in (None, {}, replace(self.frame, rails=list(self.frame.rails)),
                      replace(self.frame, rails=(None,))):
            self.assertEqual(PowerGuard(self.profile).observe(frame, now_s=0)["status"], "TRIPPED")

    def test_profile_cannot_hide_bad_configuration(self):
        for changes in ({"rate_mts": 8000}, {"rate_mts": True}, {"generation": "DDR6"},
                        {"rails": ()}, {"rails": self.profile.rails + self.profile.rails},
                        {"max_sample_gap_s": 0}, {"evidence_ref": ""},
                        {"rails": (self.profile.rails[0],)}, {"evidence_kind": "certified"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.profile, **changes)

    def test_invalid_rail_configuration(self):
        rail = self.profile.rails[1]
        for changes in ({"min_voltage_v": rail.max_voltage_v}, {"max_current_a": 0},
                        {"path_resistance_ohm": -1}, {"stop_temp_c": rail.min_temp_c},
                        {"accounting": "both"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(rail, **changes)

    def test_healthy_trace_and_hardware_label_never_authorize(self):
        for kind in ("synthetic", "hardware_trace_unverified"):
            payload = copy.deepcopy(self.payload)
            payload["profile"]["evidence_kind"] = kind
            report = review_trace(payload)
            self.assertEqual(report["observations_checked"], 3)
            self.assertFalse(report["hardware_authorized"])
            self.assertFalse(report["lifetime_proven"])

    def test_trace_stops_at_first_fault(self):
        self.payload["observations"][1]["frame"]["rails"][1]["current_a"] = 100
        report = review_trace(self.payload)
        self.assertEqual(report["status"], "TRIPPED")
        self.assertEqual(report["observations_checked"], 2)
        self.assertEqual(report["observations_supplied"], 3)

    def test_unknown_fields_empty_trace_and_version_refused(self):
        for changes in ({"schema_version": True}, {"schema_version": 2},
                        {"observations": []}, {"apply": True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                review_trace(self.payload | changes)

    def test_json_round_trip(self):
        self.assertEqual(review_trace(json.loads(json.dumps(self.payload))), review_trace(self.payload))

    def test_cli_status_codes_and_no_apply_flag(self):
        root = Path(__file__).resolve().parents[2]
        command = [sys.executable, "-S", "-m", "motionbricks.prebios_power"]
        with tempfile.TemporaryDirectory() as tmp:
            trace = Path(tmp) / "trace.json"
            for expected, current in ((0, 2), (1, 100)):
                self.payload["observations"][0]["frame"]["rails"][1]["current_a"] = current
                trace.write_text(json.dumps(self.payload), encoding="utf-8")
                result = subprocess.run(command + ["--trace", str(trace)], cwd=root,
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertFalse(json.loads(result.stdout)["hardware_applied"])
            trace.write_text("{}", encoding="utf-8")
            result = subprocess.run(command + ["--trace", str(trace)], cwd=root,
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)["status"], "INVALID_INPUT")
        result = subprocess.run(command + ["--apply"], cwd=root, capture_output=True,
                                text=True, timeout=10)
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
