"""Dependency-free, explicitly uncalibrated cockroach/home agent model.

Run with ``python -S -m motionbricks.roach_home --help``. Model ticks and
cells have no fitted physical duration/size. No MotionBricks weights are used.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
import csv
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import statistics
import sys

MODEL_VERSION = "roach-home-0.1"
SCENARIOS = ("baseline", "constant_light", "no_food", "no_water", "no_shelters", "no_social")
MOVES = ((0, 0), (1, 0), (0, 1), (-1, 0), (0, -1))
Point = tuple[int, int]


@dataclass(frozen=True)
class House:
    name: str
    grid: tuple[str, ...]
    rooms: tuple[tuple[str, tuple[int, int, int, int]], ...]

    def __post_init__(self):
        if not isinstance(self.name, str) or not 1 <= len(self.name) <= 100:
            raise ValueError("house name must contain 1..100 characters")
        if not 5 <= len(self.grid) <= 80 or not all(isinstance(r, str) for r in self.grid):
            raise ValueError("grid must contain 5..80 text rows")
        width = len(self.grid[0])
        if not 5 <= width <= 80 or any(len(r) != width for r in self.grid):
            raise ValueError("grid must be rectangular, width 5..80")
        if any(c not in "#.sfw" for row in self.grid for c in row):
            raise ValueError("allowed cells: # wall/furniture, . floor, s shelter, f food, w water")
        if any(c != "#" for c in self.grid[0] + self.grid[-1]) or any(
            row[0] != "#" or row[-1] != "#" for row in self.grid
        ):
            raise ValueError("outer boundary must be closed")
        floor = self.cells()
        if not floor:
            raise ValueError("house needs walkable floor")
        seen = {floor[0]}
        queue = deque(seen)
        while queue:
            for p in self.neighbors(queue.popleft()):
                if p not in seen:
                    seen.add(p)
                    queue.append(p)
        if len(seen) != len(floor):
            raise ValueError("all walkable cells must be connected through doorways")
        names = set()
        for name, bounds in self.rooms:
            if not isinstance(name, str) or not 1 <= len(name) <= 50 or name in names:
                raise ValueError("room names must be unique text, 1..50 characters")
            names.add(name)
            if len(bounds) != 4 or any(type(v) is not int for v in bounds):
                raise ValueError("room bounds must be four integers")
            x0, y0, x1, y1 = bounds
            if not (0 <= x0 <= x1 < width and 0 <= y0 <= y1 < len(self.grid)):
                raise ValueError("room bounds outside grid")
        for x, y in floor:
            if sum(x0 <= x <= x1 and y0 <= y <= y1 for _, (x0, y0, x1, y1) in self.rooms) != 1:
                raise ValueError("each floor cell must belong to exactly one room")

    def cells(self, symbol: str | None = None) -> list[Point]:
        return [(x, y) for y, row in enumerate(self.grid) for x, c in enumerate(row)
                if (c != "#" if symbol is None else c == symbol)]

    def walkable(self, p: Point) -> bool:
        x, y = p
        return 0 <= y < len(self.grid) and 0 <= x < len(self.grid[0]) and self.grid[y][x] != "#"

    def neighbors(self, p: Point) -> list[Point]:
        x, y = p
        return [(x + dx, y + dy) for dx, dy in MOVES[1:] if self.walkable((x + dx, y + dy))]

    def room_at(self, p: Point) -> str:
        return next(name for name, (x0, y0, x1, y1) in self.rooms
                    if x0 <= p[0] <= x1 and y0 <= p[1] <= y1)

    def to_dict(self) -> dict:
        return {"name": self.name, "grid": list(self.grid),
                "rooms": [{"name": n, "bounds": list(b)} for n, b in self.rooms]}

    @classmethod
    def from_dict(cls, value: dict) -> House:
        try:
            return cls(value["name"], tuple(value["grid"]),
                       tuple((r["name"], tuple(r["bounds"])) for r in value["rooms"]))
        except (KeyError, TypeError) as exc:
            raise ValueError("invalid house schema") from exc


def default_house() -> House:
    grid = [["."] * 41 for _ in range(29)]
    for y in range(29):
        for x in range(41):
            if x in (0, 40) or y in (0, 28) or x == 20 or y == 14:
                grid[y][x] = "#"
    # Four room connections; a doorway belongs to the adjacent named room.
    for y in (6, 7, 8, 20, 21, 22):
        grid[y][20] = "."
    for x in (8, 9, 30, 31):
        grid[14][x] = "."
    for x0, y0, x1, y1 in ((3, 3, 5, 6), (10, 4, 13, 6), (34, 3, 37, 5),
                            (3, 21, 10, 23), (29, 18, 36, 23)):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                grid[y][x] = "#"
    for x0, y, length in ((2, 1, 6), (33, 1, 6), (2, 27, 7), (29, 24, 8)):
        for x in range(x0, x0 + length):
            grid[y][x] = "s"
    grid[3][8] = "f"
    grid[25][12] = "f"
    grid[2][7] = "w"
    grid[6][35] = "w"
    return House("虚拟民宅 · 四室行为观察", tuple("".join(r) for r in grid), (
        ("厨房", (0, 0, 20, 14)), ("卫生间", (21, 0, 40, 14)),
        ("客厅", (0, 15, 20, 28)), ("卧室", (21, 15, 40, 28))))


@dataclass(frozen=True)
class Config:
    agents: int = 40
    steps: int = 720
    seed: int = 1
    sample_every: int = 1
    cycle: int = 240
    light_ticks: int = 120
    sensor_range: int = 8
    wall_weight: float = 1.2
    light_weight: float = 2.0
    shelter_weight: float = 1.6
    social_weight: float = 0.6
    crowd_weight: float = 0.04
    food_weight: float = 3.0
    water_weight: float = 3.0

    def __post_init__(self):
        for name, lo, hi in (("agents", 1, 200), ("steps", 1, 7200), ("seed", 0, 2**32 - 1),
                             ("sample_every", 1, 7200), ("cycle", 2, 7200),
                             ("light_ticks", 0, 7200), ("sensor_range", 1, 30)):
            v = getattr(self, name)
            if type(v) is not int or not lo <= v <= hi:
                raise ValueError(f"{name} must be an integer in [{lo}, {hi}]")
        if self.light_ticks > self.cycle:
            raise ValueError("light_ticks cannot exceed cycle")
        for name in ("wall_weight", "light_weight", "shelter_weight", "social_weight",
                     "crowd_weight", "food_weight", "water_weight"):
            v = getattr(self, name)
            if type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 20:
                raise ValueError(f"{name} must be finite in [0, 20]")
        if self.agents * (2 + self.steps // self.sample_every) > 300_000:
            raise ValueError("trajectory exceeds 300000 agent samples; increase sample_every")


def resource_field(house: House, symbol: str, radius: int) -> dict[Point, float]:
    """Finite-range graph-distance proxy, not a measured odor/airflow field."""
    distances = dict.fromkeys(house.cells(symbol), 0)
    queue = deque(distances)
    while queue:
        p = queue.popleft()
        if distances[p] >= radius:
            continue
        for q in house.neighbors(p):
            if q not in distances:
                distances[q] = distances[p] + 1
                queue.append(q)
    return {p: math.exp(-d / 4) for p, d in distances.items()}


def apply_scenario(house: House, config: Config, scenario: str) -> tuple[House, Config]:
    if scenario not in SCENARIOS:
        raise ValueError("unknown scenario")
    symbol = {"no_food": "f", "no_water": "w", "no_shelters": "s"}.get(scenario)
    if symbol:
        house = replace(house, grid=tuple(r.replace(symbol, ".") for r in house.grid))
    if scenario == "no_social":
        config = replace(config, social_weight=0)
    return house, config


def simulate(config: Config, house: House | None = None, scenario: str = "baseline") -> dict:
    house, config = apply_scenario(house or default_house(), config, scenario)
    rng = random.Random(config.seed)
    floor = house.cells()
    positions = [rng.choice(floor) for _ in range(config.agents)]
    hunger = [rng.random() for _ in positions]
    thirst = [rng.random() for _ in positions]
    previous = [(0, 0)] * config.agents
    food = resource_field(house, "f", config.sensor_range)
    water = resource_field(house, "w", config.sensor_range)
    near_wall = {p: len(house.neighbors(p)) < 4 for p in floor}
    neighbors = {p: [p] + house.neighbors(p) for p in floor}
    rooms = {p: house.room_at(p) for p in floor}
    heat = Counter()
    rows, frames = [], [{"tick": 0, "positions": [list(p) for p in positions]}]
    for tick in range(1, config.steps + 1):
        light_on = scenario == "constant_light" or (tick - 1) % config.cycle < config.light_ticks
        light = 0.9 if light_on else 0.06
        occupancy = Counter(positions)  # synchronous snapshot, before any move
        new_positions = []
        moved = food_contacts = water_contacts = 0
        for i, current in enumerate(positions):
            # Always consume two draws, keeping paired scenarios aligned by tick/id.
            gate, choice = rng.random(), rng.random()
            hunger[i] = min(1.0, hunger[i] + 0.008)
            thirst[i] = min(1.0, thirst[i] + 0.012)
            candidates = neighbors[current]
            scores = []
            for p in candidates:
                shelter = house.grid[p[1]][p[0]] == "s"
                count = sum(occupancy[q] for q in neighbors[p]) - int(current in neighbors[p])
                dx, dy = p[0] - current[0], p[1] - current[1]
                persistence = 0.6 if (dx, dy) == previous[i] and p != current else 0
                score = (config.wall_weight * near_wall[p]
                         - config.light_weight * light * (0.1 if shelter else 1)
                         + config.shelter_weight * shelter
                         + config.social_weight * math.log1p(count)
                         - config.crowd_weight * count**2
                         + config.food_weight * hunger[i] * food.get(p, 0)
                         + config.water_weight * thirst[i] * water.get(p, 0)
                         + persistence + (0.8 if shelter and p == current else 0))
                scores.append(score)
            p = current
            if gate < (0.3 if light_on else 0.75):
                maximum = max(scores)
                weights = [math.exp(s - maximum) for s in scores]
                threshold = choice * sum(weights)
                for candidate, weight in zip(candidates, weights):
                    threshold -= weight
                    if threshold <= 0:
                        p = candidate
                        break
            previous[i] = (p[0] - current[0], p[1] - current[1])
            moved += p != current
            symbol = house.grid[p[1]][p[0]]
            if symbol == "f":
                hunger[i] = 0.0
                food_contacts += 1
            if symbol == "w":
                thirst[i] = 0.0
                water_contacts += 1
            new_positions.append(p)
            heat[p] += 1
        positions = new_positions
        room_counts = Counter(rooms[p] for p in positions)
        rows.append({"tick": tick, "light_on": int(light_on),
                     "moving_fraction": moved / config.agents,
                     "shelter_fraction": sum(house.grid[y][x] == "s" for x, y in positions) / config.agents,
                     "wall_fraction": sum(near_wall[p] for p in positions) / config.agents,
                     "food_contact_agent_ticks": food_contacts,
                     "water_contact_agent_ticks": water_contacts,
                     **{f"room:{n}": room_counts[n] for n, _ in house.rooms}})
        if tick % config.sample_every == 0 or tick == config.steps:
            frames.append({"tick": tick, "positions": [list(p) for p in positions]})
    tail = rows[config.steps // 2:]
    summary = {key: statistics.fmean(row[key] for row in tail)
               for key in ("moving_fraction", "shelter_fraction", "wall_fraction")}
    summary.update({"analysis_start_tick": tail[0]["tick"], "analysis_end_tick": config.steps,
                    "food_contact_agent_ticks": sum(r["food_contact_agent_ticks"] for r in rows),
                    "water_contact_agent_ticks": sum(r["water_contact_agent_ticks"] for r in rows)})
    specification = {"version": MODEL_VERSION, "scenario": scenario,
                     "config": asdict(config), "house": house.to_dict()}
    return {**specification, "status": "SYNTHETIC_UNCALIBRATED",
            "empirical_validation": "NOT_RUN", "physical_time_calibrated": False,
            "specification_sha256": hashlib.sha256(canonical(specification).encode()).hexdigest(),
            "runtime": {"python": platform.python_version(), "platform": platform.platform()},
            "summary": summary, "metrics": rows, "frames": frames,
            "heat": [[heat[(x, y)] for x in range(len(house.grid[0]))] for y in range(len(house.grid))]}


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def write_csv(path: Path, rows: list[dict]):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def export(result: dict, out: Path):
    # An experiment directory is immutable by default; accidental overwrite is refused.
    out.mkdir(parents=True, exist_ok=False)
    (out / "run.json").write_text(canonical(result) + "\n", encoding="utf-8")
    write_csv(out / "metrics.csv", result["metrics"])
    from .roach_home_view import render_html
    (out / "observe.html").write_text(render_html(result), encoding="utf-8")
    write_manifest(out)


def write_manifest(out: Path):
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(out.iterdir()) if p.is_file() and p.name != "sha256.json"}
    (out / "sha256.json").write_text(canonical(hashes) + "\n", encoding="utf-8")


def compare(config: Config, house: House, seeds: list[int], out: Path):
    if not seeds or len(seeds) > 20 or len(set(seeds)) != len(seeds):
        raise ValueError("comparison needs 1..20 distinct seeds")
    configs = [replace(config, seed=s) for s in seeds]
    if config.agents * config.steps * len(seeds) * len(SCENARIOS) > 20_000_000:
        raise ValueError("comparison exceeds 20000000 agent-ticks")
    if out.exists():
        raise FileExistsError(out)
    records = []
    for cfg in configs:
        baseline = None
        for scenario in SCENARIOS:
            summary = simulate(cfg, house, scenario)["summary"]
            if baseline is None:
                baseline = summary
            records.append({"seed": cfg.seed, "scenario": scenario, **summary,
                            **{f"delta_{k}": summary[k] - baseline[k]
                               for k in ("moving_fraction", "shelter_fraction", "wall_fraction")}})
    out.mkdir(parents=True, exist_ok=False)
    write_csv(out / "replicates.csv", records)
    aggregates = []
    for scenario in SCENARIOS:
        group = [r for r in records if r["scenario"] == scenario]
        for metric in ("moving_fraction", "shelter_fraction", "wall_fraction"):
            deltas = [r[f"delta_{metric}"] for r in group]
            aggregates.append({"scenario": scenario, "metric": metric, "n_seeds": len(seeds),
                               "mean": statistics.fmean(r[metric] for r in group),
                               "paired_delta_mean": statistics.fmean(deltas),
                               "paired_delta_sd": statistics.stdev(deltas) if len(deltas) > 1 else None})
    write_csv(out / "comparison.csv", aggregates)
    (out / "specification.json").write_text(canonical({"version": MODEL_VERSION,
        "config": asdict(config), "house": house.to_dict(), "seeds": seeds,
        "scenarios": list(SCENARIOS), "status": "SYNTHETIC_UNCALIBRATED",
        "empirical_validation": "NOT_RUN", "runtime": {"python": platform.python_version(),
        "platform": platform.platform()}}) + "\n", encoding="utf-8")
    write_manifest(out)
    return aggregates


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True, help="new output directory")
    parser.add_argument("--config", type=Path, help="JSON object of Config fields")
    parser.add_argument("--house", type=Path, help="house JSON; see experiments/roach_home/apartment.json")
    parser.add_argument("--agents", type=int)
    parser.add_argument("--steps", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--sample-every", type=int)
    parser.add_argument("--scenario", choices=SCENARIOS, default="baseline")
    parser.add_argument("--compare", action="store_true", help="run all six scenarios with paired seeds")
    parser.add_argument("--seeds", default="1,2,3,4,5", help="comma-separated comparison seeds")
    args = parser.parse_args(argv)
    try:
        values = json.loads(args.config.read_text(encoding="utf-8")) if args.config else {}
        values.update({k: getattr(args, k) for k in ("agents", "steps", "seed", "sample_every")
                       if getattr(args, k) is not None})
        config = Config(**values)
        house = House.from_dict(json.loads(args.house.read_text(encoding="utf-8"))) if args.house else default_house()
        if args.compare:
            if args.scenario != "baseline" or args.seed is not None:
                raise ValueError("--compare uses --seeds and all scenarios; omit --seed/--scenario")
            result = compare(config, house, [int(s) for s in args.seeds.split(",")], args.out_dir)
            print(canonical({"status": "SYNTHETIC_UNCALIBRATED", "comparison": result}))
        else:
            result = simulate(config, house, args.scenario)
            export(result, args.out_dir)
            print(canonical({"status": result["status"], "summary": result["summary"],
                             "out_dir": str(args.out_dir)}))
        return 0
    except (ValueError, TypeError, OSError) as exc:
        print(canonical({"status": "REFUSED", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
