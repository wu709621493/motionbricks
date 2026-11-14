"""Software invariants and export contracts; these do not validate biology."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from motionbricks.roach_home import (Config, House, SCENARIOS, apply_scenario,
    compare, default_house, export, resource_field, simulate)
from motionbricks.roach_home_view import render_html


class HomeTests(unittest.TestCase):
    def test_house_round_trip_and_room_coverage(self):
        h = default_house()
        self.assertEqual(House.from_dict(h.to_dict()), h)
        self.assertEqual(len({h.room_at(p) for p in h.cells()}), 4)
        for p in ((20, 7), (8, 14), (30, 14), (20, 21)):
            self.assertTrue(h.walkable(p))

    def test_open_boundary_and_disconnected_house_rejected(self):
        for rows in (("##.##", "#...#", "#...#", "#...#", "#####"),
                     ("#####", "#.#.#", "#.#.#", "#.#.#", "#####")):
            with self.assertRaises(ValueError):
                House("invalid", rows, (("room", (0, 0, 4, 4)),))

    def test_invalid_config_refused(self):
        for values in ({"agents": True}, {"agents": 201}, {"steps": 0},
                       {"light_weight": float("nan")}, {"wall_weight": float("inf")},
                       {"social_weight": -1}, {"light_ticks": 241}, {"seed": -1},
                       {"steps": 7200, "agents": 200, "sample_every": 1}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                Config(**values)

    def test_resources_do_not_cross_walls_or_exceed_sensor_range(self):
        h = House("maze", ("#######", "#f#...#", "#.#...#", "#.....#", "#######"),
                  (("room", (0, 0, 6, 4)),))
        field = resource_field(h, "f", 4)
        self.assertNotIn((3, 1), field)  # nearby in Euclidean distance, far by doorway
        self.assertIn((3, 3), field)
        self.assertNotIn((4, 3), field)

    def test_seed_reproducibility_and_variation(self):
        cfg = Config(steps=50, agents=8)
        a = simulate(cfg)
        self.assertEqual(a, simulate(cfg))
        self.assertNotEqual(a["frames"], simulate(replace(cfg, seed=2))["frames"])

    def test_population_wall_and_per_step_motion_invariants(self):
        h = default_house()
        for scenario in SCENARIOS:
            run = simulate(Config(steps=70, agents=12, sample_every=1), h, scenario)
            self.assertEqual(sum(map(sum, run["heat"])), 70 * 12)
            for frame in run["frames"]:
                self.assertEqual(len(frame["positions"]), 12)
                self.assertTrue(all(h.walkable(tuple(p)) for p in frame["positions"]))
            for a, b in zip(run["frames"], run["frames"][1:]):
                self.assertTrue(all(abs(x-u) + abs(y-v) <= 1
                                    for (x, y), (u, v) in zip(a["positions"], b["positions"])))
            self.assertTrue(all(sum(v for k, v in row.items() if k.startswith("room:")) == 12
                                for row in run["metrics"]))

    def test_paired_initial_states_unchanged_and_no_resource_contacts(self):
        cfg = Config(steps=30)
        baseline = simulate(cfg)
        for scenario in SCENARIOS:
            run = simulate(cfg, scenario=scenario)
            self.assertEqual(run["frames"][0], baseline["frames"][0])
            self.assertEqual(run["empirical_validation"], "NOT_RUN")
        self.assertEqual(simulate(cfg, scenario="no_food")["summary"]["food_contact_agent_ticks"], 0)
        self.assertEqual(simulate(cfg, scenario="no_water")["summary"]["water_contact_agent_ticks"], 0)
        self.assertEqual(simulate(cfg, scenario="no_shelters")["summary"]["shelter_fraction"], 0)

    def test_light_schedule_and_final_sample(self):
        r = simulate(Config(steps=7, cycle=4, light_ticks=2, sample_every=3))
        self.assertEqual([x["light_on"] for x in r["metrics"]], [1, 1, 0, 0, 1, 1, 0])
        self.assertEqual([x["tick"] for x in r["frames"]], [0, 3, 6, 7])
        self.assertTrue(all(x["light_on"] for x in simulate(Config(steps=8), scenario="constant_light")["metrics"]))

    def test_unknown_scenario_rejected(self):
        with self.assertRaises(ValueError):
            apply_scenario(default_house(), Config(), "invented")

    def test_output_hashes_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "run"
            export(simulate(Config(steps=10)), out)
            for name, digest in json.loads((out / "sha256.json").read_text(encoding="utf-8")).items():
                self.assertEqual(hashlib.sha256((out / name).read_bytes()).hexdigest(), digest)
            self.assertEqual(json.loads((out / "run.json").read_text(encoding="utf-8"))["status"], "SYNTHETIC_UNCALIBRATED")
            with self.assertRaises(FileExistsError):
                export(simulate(Config(steps=1)), out)

    def test_html_escapes_user_text_and_is_offline(self):
        run = simulate(Config(steps=1))
        run["house"]["name"] = "</script><script>alert(1)</script>"
        html = render_html(run)
        self.assertNotIn("</script><script>alert", html)
        self.assertNotIn("__RUN_DATA__", html)
        self.assertNotIn("fetch(", html)
        self.assertNotIn('<script src=', html)

    def test_comparison_uses_distinct_seeds_and_baseline_deltas(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "compare"
            rows = compare(Config(steps=10, agents=3), default_house(), [1, 2], out)
            self.assertEqual(len(rows), 18)
            self.assertTrue(all(r["paired_delta_mean"] == 0 for r in rows if r["scenario"] == "baseline"))
            with self.assertRaises(ValueError):
                compare(Config(steps=1), default_house(), [1, 1], Path(d) / "bad")

    def test_cli_stdlib_only_and_invalid_input(self):
        with tempfile.TemporaryDirectory() as d:
            p = subprocess.run([sys.executable, "-S", "-m", "motionbricks.roach_home",
                "--steps", "4", "--out-dir", str(Path(d) / "run")],
                capture_output=True, text=True, timeout=10)
            self.assertEqual(p.returncode, 0, p.stderr)
            p = subprocess.run([sys.executable, "-S", "-m", "motionbricks.roach_home",
                "--agents", "0", "--out-dir", str(Path(d) / "bad")],
                capture_output=True, text=True, timeout=10)
            self.assertEqual(p.returncode, 2)
            self.assertEqual(json.loads(p.stderr)["status"], "REFUSED")
            self.assertFalse((Path(d) / "bad").exists())

    def test_cli_rejects_non_object_config_as_structured_refusal(self):
        with tempfile.TemporaryDirectory() as d:
            config = Path(d) / "config.json"
            out = Path(d) / "run"
            for value in ([], None, 1, "config"):
                with self.subTest(value=value):
                    config.write_text(json.dumps(value), encoding="utf-8")
                    p = subprocess.run([sys.executable, "-S", "-m", "motionbricks.roach_home",
                        "--config", str(config), "--out-dir", str(out)],
                        capture_output=True, text=True, timeout=10)
                    self.assertEqual(p.returncode, 2, p.stderr)
                    self.assertEqual(json.loads(p.stderr)["status"], "REFUSED")
                    self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
