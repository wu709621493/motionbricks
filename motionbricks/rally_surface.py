"""Standard-library, uncalibrated road-surface screening; no race controller.

Synthetic route segments are independent steady manoeuvres, not a trajectory.
The erosion outputs are dimensionless proxies, not sediment mass predictions.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path

G = 9.80665
EVIDENCE = "SYNTHETIC_UNCALIBRATED"


def number(value, name, low=0.0, high=1e12):
    if type(value) not in (int, float):
        raise ValueError(f"{name}: finite number required")
    # Range-check before isfinite so enormous JSON integers do not overflow.
    if not low <= value <= high or not math.isfinite(value):
        raise ValueError(f"{name}: must be in [{low}, {high}]")


def integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name}: integer in [{low}, {high}] required")


def text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name}: nonempty text required")


def blend(dry, wet, saturation):
    return dry + (wet - dry) * saturation


@dataclass(frozen=True)
class Segment:
    length_m: float
    grade: float  # rise / horizontal run; signed in the driving direction
    radius_m: float | None  # None is straight, zero is invalid
    width_m: float

    def __post_init__(self):
        number(self.length_m, "length_m", 0.001, 1e6)
        number(self.grade, "grade", -0.5, 0.5)
        number(self.width_m, "width_m", 0.1, 100)
        if self.radius_m is not None:
            number(self.radius_m, "radius_m", 0.1, 1e7)


@dataclass(frozen=True)
class Soil:
    cohesion_dry_pa: float
    cohesion_wet_pa: float
    phi_dry_deg: float
    phi_wet_deg: float
    bearing_dry_pa: float
    bearing_wet_pa: float

    def __post_init__(self):
        for key, value in asdict(self).items():
            number(value, key, 0, 80 if "phi" in key else 1e8)
        if min(self.bearing_dry_pa, self.bearing_wet_pa) <= 0:
            raise ValueError("bearing strength must be positive")


@dataclass(frozen=True)
class Surface:
    name: str
    tire_mu_dry: float
    tire_mu_wet: float
    support_area_m2: float
    support_floor_m2: float
    retention_loss_per_pass: float
    runoff_coefficient: float
    erodibility: float
    cover_fraction: float
    rolling_coefficient: float
    interface_mu_dry: float | None = None
    interface_mu_wet: float | None = None
    anchor_capacity_n: float = 0
    sheet_capacity_n: float | None = None

    def __post_init__(self):
        text(self.name, "surface name")
        for key in ("tire_mu_dry", "tire_mu_wet", "rolling_coefficient"):
            number(getattr(self, key), key, 0, 3)
        for key in ("runoff_coefficient", "erodibility", "cover_fraction",
                    "retention_loss_per_pass"):
            number(getattr(self, key), key, 0, 1)
        number(self.support_area_m2, "support_area_m2", 0.001, 100)
        number(self.support_floor_m2, "support_floor_m2", 0.001,
               self.support_area_m2)
        number(self.anchor_capacity_n, "anchor_capacity_n", 0, 1e7)
        if (self.interface_mu_dry is None) != (self.interface_mu_wet is None):
            raise ValueError("both interface coefficients are required together")
        if self.interface_mu_dry is not None:
            number(self.interface_mu_dry, "interface_mu_dry", 0, 3)
            number(self.interface_mu_wet, "interface_mu_wet", 0, 3)
            if self.sheet_capacity_n is None:
                raise ValueError("exposed sheets require sheet_capacity_n")
        elif self.anchor_capacity_n or self.sheet_capacity_n is not None:
            raise ValueError("sheet/anchor capacity requires an interface")
        if self.sheet_capacity_n is not None:
            number(self.sheet_capacity_n, "sheet_capacity_n", 0, 1e8)


@dataclass(frozen=True)
class Scenario:
    mass_kg: float
    speed_m_s: float
    acceleration_m_s2: float
    saturation: float
    rain_mm: float
    previous_passes: int
    protected_routing_fraction: float

    def __post_init__(self):
        number(self.mass_kg, "mass_kg", 1, 1e5)
        number(self.speed_m_s, "speed_m_s", 0, 100)
        number(self.acceleration_m_s2, "acceleration_m_s2", -30, 30)
        number(self.saturation, "saturation", 0, 1)
        number(self.rain_mm, "rain_mm", 0, 1000)
        integer(self.previous_passes, "previous_passes", 0, 100000)
        number(self.protected_routing_fraction, "protected_routing_fraction", 0, 1)


def evaluate(segment: Segment, soil: Soil, surface: Surface, case: Scenario):
    """Evaluate one fixed-speed demand; exceeding capacity does not change speed.

    N is whole-vehicle normal load, A an assumed whole-vehicle shear/support
    footprint (not tire contact area). Anchors only raise the interface limit;
    they never bypass the common soil limit. No pore pressure is solved.
    """
    theta = math.atan(segment.grade)
    normal_n = case.mass_kg * G * math.cos(theta)
    retention = math.exp(-surface.retention_loss_per_pass * case.previous_passes)
    area = surface.support_floor_m2 + (
        surface.support_area_m2 - surface.support_floor_m2) * retention
    cohesion = blend(soil.cohesion_dry_pa, soil.cohesion_wet_pa, case.saturation)
    phi = math.radians(blend(soil.phi_dry_deg, soil.phi_wet_deg, case.saturation))
    tire_mu = blend(surface.tire_mu_dry, surface.tire_mu_wet, case.saturation)
    # Residual roughness is an explicit toy assumption, not a measured wear law.
    tire_mu *= 0.6 + 0.4 * retention
    capacities = {
        "tire": tire_mu * normal_n,
        "ground_shear": cohesion * area + normal_n * math.tan(phi),
    }
    if surface.interface_mu_dry is not None:
        interface_mu = blend(surface.interface_mu_dry, surface.interface_mu_wet,
                             case.saturation)
        capacities["sheet_sliding"] = (interface_mu * normal_n
                                        + surface.anchor_capacity_n * retention)
        capacities["sheet_strength"] = surface.sheet_capacity_n * retention
    capacity = min(capacities.values())
    longitudinal_n = case.mass_kg * (
        case.acceleration_m_s2 + G * math.sin(theta)
        + surface.rolling_coefficient * G * math.cos(theta))
    lateral_n = (0.0 if segment.radius_m is None else
                 case.mass_kg * case.speed_m_s ** 2 / segment.radius_m)
    demand_n = math.hypot(longitudinal_n, lateral_n)
    bearing_pa = blend(soil.bearing_dry_pa, soil.bearing_wet_pa, case.saturation)
    bearing_ratio = normal_n / (area * bearing_pa)
    # length_m is slope-following chainage; rain falls on its horizontal projection.
    plan_area_m2 = segment.length_m * math.cos(theta) * segment.width_m
    rainfall_m3 = case.rain_mm / 1000 * plan_area_m2
    runoff_m3 = rainfall_m3 * surface.runoff_coefficient
    routed_m3 = runoff_m3 * case.protected_routing_fraction
    unmanaged_m3 = runoff_m3 - routed_m3
    slope_weight = 1 + 5 * abs(segment.grade)  # deliberately uncalibrated
    road_index = (segment.length_m / 1000 * case.rain_mm / 30 * slope_weight
                  * surface.erodibility * (1 - surface.cover_fraction * retention))
    slope_index = unmanaged_m3 / 100 * slope_weight
    return {
        "effective_mu": capacity / normal_n,
        "capacity_n": capacity,
        "demand_n": demand_n,
        "margin_n": capacity - demand_n,
        "limiting_interfaces": [key for key, value in capacities.items()
                                if math.isclose(value, capacity, rel_tol=1e-10)],
        "demand_exceeded": demand_n > capacity,
        "bearing_ratio": bearing_ratio,
        "bearing_exceeded": bearing_ratio > 1,
        "retention": retention,
        "rainfall_m3": rainfall_m3,
        "non_runoff_m3": rainfall_m3 - runoff_m3,
        "runoff_m3": runoff_m3,
        "protected_runoff_m3": routed_m3,
        "unprotected_runoff_m3": unmanaged_m3,
        "road_detachment_index": road_index,
        "downslope_exposure_index": slope_index,
    }


def make_route(spec):
    """One straight and one bend per cycle; no GPS or film geometry is inferred."""
    expected = {"id", "geometry_evidence", "scale_source_url", "length_m", "corners",
                "width_m", "grade_mean", "grade_amplitude", "radius_min_m",
                "radius_max_m"}
    if set(spec) != expected:
        raise ValueError("route keys differ from schema")
    for key in ("id", "scale_source_url"):
        text(spec[key], key)
    if spec["geometry_evidence"] != "SYNTHETIC_NOT_A_SURVEY":
        raise ValueError("generated geometry must remain marked synthetic")
    integer(spec["corners"], "corners", 1, 10000)
    number(spec["length_m"], "length_m", 1, 1e6)
    number(spec["grade_mean"], "grade_mean", -0.4, 0.4)
    number(spec["grade_amplitude"], "grade_amplitude", 0, 0.1)
    number(spec["radius_min_m"], "radius_min_m", 1, 1e6)
    number(spec["radius_max_m"], "radius_max_m", spec["radius_min_m"], 1e6)
    count = spec["corners"]
    length = spec["length_m"] / (count * 2)
    result = []
    for i in range(count):
        phase = i / count * 2 * math.pi
        grade = spec["grade_mean"] + spec["grade_amplitude"] * math.sin(phase)
        # Integer cycling avoids random-state and random-generator dependencies.
        radius = spec["radius_min_m"] + ((i * 37) % 101) / 100 * (
            spec["radius_max_m"] - spec["radius_min_m"])
        result.extend((Segment(length, grade, None, spec["width_m"]),
                       Segment(length, grade, radius, spec["width_m"])))
    return tuple(result)


def summarize(route, soil, surface, case):
    if not route:
        raise ValueError("route must contain at least one segment")
    total = math.fsum(segment.length_m for segment in route)
    values = [evaluate(segment, soil, surface, case) for segment in route]
    result = {
        "minimum_mu": min(v["effective_mu"] for v in values),
        "minimum_margin_n": min(v["margin_n"] for v in values),
        "demand_exceeded_length_fraction": math.fsum(
            s.length_m for s, v in zip(route, values) if v["demand_exceeded"]) / total,
        "bearing_exceeded_length_fraction": math.fsum(
            s.length_m for s, v in zip(route, values) if v["bearing_exceeded"]) / total,
    }
    for key in ("rainfall_m3", "non_runoff_m3", "runoff_m3", "protected_runoff_m3",
                "unprotected_runoff_m3", "road_detachment_index", "downslope_exposure_index"):
        result[key] = math.fsum(v[key] for v in values)
    for key in ("runoff_m3", "unprotected_runoff_m3", "road_detachment_index",
                "downslope_exposure_index"):
        result[key + "_per_km"] = result[key] / (total / 1000)
    return {key: round(value, 8) for key, value in result.items()}


def run_study(config):
    expected = {"schema_version", "parameter_evidence", "notes", "sources", "soil",
                "vehicle", "routes", "surfaces", "weather", "passes",
                "protected_routing_fractions"}
    if set(config) != expected or type(config["schema_version"]) is not int or config["schema_version"] != 1:
        raise ValueError("unsupported study schema")
    if config["parameter_evidence"] != EVIDENCE:
        raise ValueError("this model only accepts explicitly uncalibrated studies")
    for key in ("routes", "surfaces", "weather", "passes", "protected_routing_fractions"):
        if not isinstance(config[key], list) or not config[key]:
            raise ValueError(f"{key}: nonempty list required")
    if math.prod(len(config[k]) for k in ("routes", "surfaces", "weather", "passes",
                                         "protected_routing_fractions")) > 1000:
        raise ValueError("study exceeds 1000-case resource bound")
    soil = Soil(**config["soil"])
    surfaces = [Surface(**entry) for entry in config["surfaces"]]
    if len({s.name for s in surfaces}) != len(surfaces):
        raise ValueError("duplicate surface names")
    if len({r["id"] for r in config["routes"]}) != len(config["routes"]):
        raise ValueError("duplicate route ids")
    for weather in config["weather"]:
        if set(weather) != {"id", "saturation", "rain_mm"}:
            raise ValueError("weather keys differ from schema")
        text(weather["id"], "weather id")
    if len({w["id"] for w in config["weather"]}) != len(config["weather"]):
        raise ValueError("duplicate weather ids")
    rows = []
    route_hashes = {}
    for spec in config["routes"]:
        route = make_route(spec)
        route_hashes[spec["id"]] = hashlib.sha256(json.dumps(
            [asdict(s) for s in route], sort_keys=True, allow_nan=False).encode()).hexdigest()
        for surface in surfaces:
            for weather in config["weather"]:
                for passes in config["passes"]:
                    for routing in config["protected_routing_fractions"]:
                        case = Scenario(**config["vehicle"], saturation=weather["saturation"],
                                        rain_mm=weather["rain_mm"], previous_passes=passes,
                                        protected_routing_fraction=routing)
                        rows.append({"route": spec["id"], "surface": surface.name,
                                     "weather": weather["id"], "previous_passes": passes,
                                     "protected_routing_fraction": routing,
                                     **summarize(route, soil, surface, case)})
    return {"schema_version": 1, "evidence": EVIDENCE,
            "scope": "independent segment screening; not lap times or engineering certification",
            "inputs": config, "geometry_sha256": route_hashes,
            "model_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "cases": rows}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="otherwise print JSON to stdout")
    args = parser.parse_args(argv)
    try:
        if args.config.stat().st_size > 1_000_000:
            raise ValueError("config exceeds 1 MB")
        result = run_study(json.loads(args.config.read_text(encoding="utf-8")))
        output = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        parser.exit(2, f"invalid study: {exc}\n")
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
