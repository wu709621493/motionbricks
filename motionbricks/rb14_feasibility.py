"""Rb-14 phase-one mass-only forward budget; CPU / Python standard library.

All positions and noise parameters are synthetic hypotheses, never measured data.
See docs/rb14_phase1_physics_zh.md for normalization and readout protocol.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Sequence

ATOMIC_MASS_KG = 1.66053906892e-27  # CODATA 2022; not an exact SI constant
RB87_MASS_U = 86.9091805310  # NIST isotope composition table
RB87_MASS_KG = RB87_MASS_U * ATOMIC_MASS_KG
HARDWARE_STATUS = {
    "fabrication": "NOT_RUN", "capture": "NOT_RUN", "frequency_measurement": "NOT_RUN",
    "surface_characterization": "NOT_RUN", "entropy_evaluation": "NOT_RUN",
    "quantum_randomness": "NOT_RUN", "puf_security": "NOT_RUN",
}


def finite(value: float, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    if not math.isfinite(value) or (value <= 0 if positive else value < 0):
        raise ValueError(f"{name} must be finite and {'positive' if positive else 'nonnegative'}")
    return value


def integer(value: int, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in [{low}, {high}]")
    return value


@dataclass(frozen=True)
class Mode:
    family: str
    p: int
    q: int
    frequency_hz: float
    effective_mass_kg: float
    lx_m: float
    ly_m: float
    quality_factor: float

    def __post_init__(self) -> None:
        if self.family not in ("flat", "string", "membrane"):
            raise ValueError("unknown mode family")
        integer(self.p, "p", 1, 100)
        integer(self.q, "q", 1, 100)
        for key in ("frequency_hz", "effective_mass_kg", "lx_m", "ly_m", "quality_factor"):
            finite(getattr(self, key), key, positive=True)

    def weight(self, position: Sequence[float]) -> float:
        if len(position) != 2:
            raise ValueError("positions must have x,y in metres")
        x, y = position
        finite(x, "x"); finite(y, "y")
        if x > self.lx_m or y > self.ly_m:
            raise ValueError("position outside modal domain")
        if self.family == "flat":
            return 1.0
        wx = math.sin(self.p * math.pi * x / self.lx_m) ** 2
        if self.family == "string":
            return wx
        return wx * math.sin(self.q * math.pi * y / self.ly_m) ** 2

    def gradient(self, position: Sequence[float]) -> tuple[float, float]:
        self.weight(position)  # same domain validation
        x, y = position
        if self.family == "flat":
            return 0.0, 0.0
        ax, ay = self.p * math.pi / self.lx_m, self.q * math.pi / self.ly_m
        dx = ax * math.sin(2 * ax * x)
        if self.family == "string":
            return dx, 0.0
        return (dx * math.sin(ay * y) ** 2,
                ay * math.sin(2 * ay * y) * math.sin(ax * x) ** 2)


def shifts_from_weights(frequency_hz: float, effective_mass_kg: float,
                        weights: Sequence[float], max_mass_ratio: float = 1e-3) -> dict:
    finite(frequency_hz, "frequency_hz", positive=True)
    finite(effective_mass_kg, "effective_mass_kg", positive=True)
    finite(max_mass_ratio, "max_mass_ratio", positive=True)
    if max_mass_ratio > 0.01:
        raise ValueError("phase-one mass-ratio limit must be <= 0.01")
    for w in weights:
        finite(w, "weight")
        if w > 1:
            raise ValueError("peak-normalized squared weight must be <= 1")
    ratio = RB87_MASS_KG * math.fsum(weights) / effective_mass_kg
    if ratio > max_mass_ratio:
        raise ValueError("mass perturbation exceeds declared small-load limit")
    # log1p/expm1 avoid subtracting near-equal absolute frequencies.
    exact = frequency_hz * math.expm1(-0.5 * math.log1p(ratio))
    linear = -0.5 * frequency_hz * ratio
    return {"mass_ratio": ratio, "linear_shift_hz": linear,
            "frozen_mode_shift_hz": exact, "linearization_error_hz": linear - exact}


def response(modes: Sequence[Mode], positions: Sequence[Sequence[float]]) -> list[float]:
    return [shifts_from_weights(m.frequency_hz, m.effective_mass_kg,
                               [m.weight(pos) for pos in positions])["linear_shift_hz"]
            for m in modes]


@dataclass(frozen=True)
class Noise:
    name: str
    white_hz_sqrt_s: float
    floor_hz: float
    drift_hz_per_s: float
    common_fractional_sigma: float

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("noise profile name is required")
        for key in ("white_hz_sqrt_s", "floor_hz", "drift_hz_per_s", "common_fractional_sigma"):
            finite(getattr(self, key), key)
        if self.white_hz_sqrt_s == self.floor_hz == 0:
            raise ValueError("a positive independent noise term is required")

    def difference_variance(self, tau_s: float) -> float:
        finite(tau_s, "tau_s", positive=True)
        # Two equal-duration, independently noisy reference / loaded windows.
        return 2 * (self.white_hz_sqrt_s ** 2 / tau_s + self.floor_hz ** 2)


def covariance_inner(a: Sequence[float], b: Sequence[float], modes: Sequence[Mode],
                     noise: Noise, tau_s: float) -> float:
    """a^T C^-1 b; diagonal + common fractional noise (Sherman-Morrison)."""
    if not len(a) == len(b) == len(modes) or not modes:
        raise ValueError("vectors must match a nonempty list of modes")
    var = noise.difference_variance(tau_s)
    u = [math.sqrt(2) * noise.common_fractional_sigma * m.frequency_hz for m in modes]
    dot = lambda x, y: math.fsum(i * j for i, j in zip(x, y))
    return (dot(a, b) - dot(a, u) * dot(b, u) / (var + dot(u, u))) / var


def norm(vector: Sequence[float], modes: Sequence[Mode], noise: Noise, tau_s: float) -> float:
    return math.sqrt(max(0.0, covariance_inner(vector, vector, modes, noise, tau_s)))


def comparison(delta: Sequence[float], modes: Sequence[Mode], noise: Noise,
               tau_s: float, dead_time_s: float, z: float) -> dict:
    finite(dead_time_s, "dead_time_s"); finite(z, "z", positive=True)
    distance = norm(delta, modes, noise, tau_s)
    # Drift bound is common fractional drift, specified as Hz/s at the first mode.
    drift = [noise.drift_hz_per_s * (tau_s + dead_time_s)
             * m.frequency_hz / modes[0].frequency_hz for m in modes]
    lower = max(0.0, distance - norm(drift, modes, noise, tau_s))
    return {"mahalanobis_distance": distance, "drift_robust_lower_bound": lower,
            "passes_margin": lower >= z}


def noise_budget(signal_hz: float, mode: Mode, noise: Noise, tau_s: float,
                 dead_time_s: float, z: float) -> dict:
    finite(abs(signal_hz), "signal"); finite(dead_time_s, "dead_time_s")
    finite(z, "z", positive=True)
    sigma = math.sqrt(noise.difference_variance(tau_s)
                      + 2 * (mode.frequency_hz * noise.common_fractional_sigma) ** 2)
    drift = noise.drift_hz_per_s * (tau_s + dead_time_s)
    margin = z * sigma + drift
    allowed_sigma = max(0.0, (abs(signal_hz) - drift) / z)
    residual = (allowed_sigma ** 2 / 2 - noise.floor_hz ** 2
                - (mode.frequency_hz * noise.common_fractional_sigma) ** 2)
    available = abs(signal_hz) > drift and residual >= 0
    return {"sigma_difference_hz": sigma, "drift_bound_hz": drift,
            "required_signal_hz": margin,
            "allowed_sigma_difference_hz": allowed_sigma,
            "allowed_white_hz_sqrt_s": math.sqrt(residual * tau_s) if available else None,
            "floor_and_drift_allow_margin": available,
            "passes_margin": abs(signal_hz) >= margin}


def local_resolution(modes: Sequence[Mode], position: Sequence[float], noise: Noise,
                     tau_s: float) -> dict:
    jac = [tuple(-m.frequency_hz * RB87_MASS_KG / (2 * m.effective_mass_kg) * g
                 for g in m.gradient(position)) for m in modes]
    x, y = [j[0] for j in jac], [j[1] for j in jac]
    a = covariance_inner(x, x, modes, noise, tau_s)
    b = covariance_inner(x, y, modes, noise, tau_s)
    c = covariance_inner(y, y, modes, noise, tau_s)
    trace = a + c
    determinant = max(0.0, a * c - b * b)
    largest = (trace + math.hypot(a - c, 2 * b)) / 2
    smallest = determinant / largest if largest else 0.0
    # Relative rank test plus absolute threshold for vanishing derivatives at nodes.
    rank = int(largest > 1.0) + int(smallest > max(1.0, largest * 1e-12))
    if len(modes) < 2:
        rank = min(rank, 1)
    return {"fisher_rank": rank,
            "local_sigma_x_nm": math.sqrt(c / determinant) * 1e9 if rank == 2 else None,
            "local_sigma_y_nm": math.sqrt(a / determinant) * 1e9 if rank == 2 else None}


def modes_for(device: dict, family: str = "membrane") -> list[Mode]:
    indices = [(1, 1), (2, 1), (1, 2)] if family == "membrane" else [(1, 1)]
    ratio = finite(device["tension_ratio_y"], "tension_ratio_y", positive=True)
    lx, ly = device["lx_m"], device["ly_m"]
    finite(lx, "lx_m", positive=True); finite(ly, "ly_m", positive=True)
    # Ideal membrane under orthotropic tension; not a silicon FEM eigenproblem.
    return [Mode(family, p, q,
                 device["f11_hz"] * math.sqrt(((p / lx) ** 2 + ratio * (q / ly) ** 2)
                                            / ((1 / lx) ** 2 + ratio * (1 / ly) ** 2)),
                 device["effective_mass_kg"], lx, ly, device["quality_factor"])
            for p, q in indices]


def positions_for(count: int, lx: float, ly: float) -> list[tuple[float, float]]:
    """Fixed rational sites, no RNG and no entropy claim; no repeated positions."""
    integer(count, "captured count", 0, 100)
    return [((i + 1) / (count + 1) * lx,
             (((5 * i + 3) % 17) + 1) / 18 * ly) for i in range(count)]


def geometry_budget(length_m: float, thickness_m: float, density_kg_m3: float,
                    young_modulus_pa: float, poisson_ratio: float,
                    target_hz: float, tension_ratio_y: float) -> dict:
    """Simply supported square isotropic plate screen, not a silicon FEM result."""
    for key, value in (("length", length_m), ("thickness", thickness_m),
                       ("density", density_kg_m3), ("E", young_modulus_pa),
                       ("target", target_hz), ("tension_ratio_y", tension_ratio_y)):
        finite(value, key, positive=True)
    finite(poisson_ratio, "poisson_ratio")
    if poisson_ratio >= 0.5:
        raise ValueError("this plate screen requires 0 <= Poisson ratio < 0.5")
    bending = young_modulus_pa * thickness_m ** 3 / (12 * (1 - poisson_ratio ** 2))
    angular_bending_sq = bending / (density_kg_m3 * thickness_m) * (2 * (math.pi / length_m) ** 2) ** 2
    f_bending = math.sqrt(angular_bending_sq) / (2 * math.pi)
    residual = (2 * math.pi * target_hz) ** 2 - angular_bending_sq
    stress = residual * density_kg_m3 / ((1 + tension_ratio_y) * (math.pi / length_m) ** 2)
    return {"evidence_origin": "SIMULATED", "length_m": length_m, "thickness_m": thickness_m,
            "effective_mass_kg": density_kg_m3 * length_m ** 2 * thickness_m / 4,
            "thickness_to_length": thickness_m / length_m,
            "thin_plate_screen_h_over_L_le_0_1": thickness_m / length_m <= .1,
            "bending_only_f11_hz": f_bending,
            "target_frequency_hz": target_hz,
            "target_allows_nonnegative_tension": residual >= 0,
            "required_sigma_x_pa": stress if residual >= 0 else None}


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError("cannot write empty scan")
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def run(config: dict, out_dir: Path) -> dict:
    if config["schema_version"] != 1:
        raise ValueError("unsupported schema_version")
    device, scan, readout = config["device"], config["scan"], config["readout"]
    modes = modes_for(device)
    limit = device["max_mass_ratio"]
    finite(limit, "max_mass_ratio", positive=True)
    profiles = [Noise(**profile) for profile in config["noise_profiles"]]
    names = [n.name for n in profiles]
    if len(set(names)) != len(names):
        raise ValueError("duplicate noise profile name")
    selected = next(n for n in profiles if n.name == readout["comparison_profile"])
    z, gap = readout["z_margin"], readout["dead_time_s"]
    finite(z, "z_margin", positive=True); finite(gap, "dead_time_s")
    lo = finite(readout["tau_min_s"], "tau_min_s", positive=True)
    hi = finite(readout["tau_max_s"], "tau_max_s", positive=True)
    if hi <= lo:
        raise ValueError("tau_max_s must exceed tau_min_s")
    points = integer(readout["tau_points"], "tau_points", 2, 1000)
    taus = [lo * (hi / lo) ** (i / (points - 1)) for i in range(points)]
    tau = finite(readout["comparison_tau_s"], "comparison_tau_s", positive=True)
    side = integer(readout["grid_side"], "grid_side", 2, 15)
    rows = []
    for family in scan["families"]:
        for frequency in scan["frequencies_hz"]:
            for mass in scan["effective_masses_kg"]:
                m = Mode(family, 1, 1, frequency, mass, device["lx_m"], device["ly_m"],
                         device["quality_factor"])
                for count in scan["captured_counts"]:
                    pos = positions_for(count, m.lx_m, m.ly_m)
                    weights = [m.weight(p) for p in pos]
                    rows.append({"evidence_origin": "SIMULATED", "family": family,
                                 "frequency_hz": frequency, "effective_mass_kg": mass,
                                 "captured_count": count, "mean_weight": math.fsum(weights) / count if count else 0,
                                 **shifts_from_weights(frequency, mass, weights, limit)})
    noise_rows, best = [], []
    for profile in profiles:
        for count in (1, 14):
            signal = shifts_from_weights(modes[0].frequency_hz, modes[0].effective_mass_kg,
                                         [0.5] * count, limit)["linear_shift_hz"]
            cases = []
            for t in taus:
                row = {"evidence_origin": "SIMULATED", "profile": profile.name,
                       "count": count, "mean_weight": 0.5, "tau_s": t, "signal_hz": signal,
                       **noise_budget(signal, modes[0], profile, t, gap, z)}
                noise_rows.append(row); cases.append(row)
            optimal = min(cases, key=lambda row: row["required_signal_hz"])
            passed = [row["tau_s"] for row in cases if row["passes_margin"]]
            best.append({"profile": profile.name, "count": count,
                         "grid_best_tau_s": optimal["tau_s"],
                         "grid_best_required_signal_hz": optimal["required_signal_hz"],
                         "any_grid_time_passes": bool(passed),
                         "first_passing_tau_s": min(passed) if passed else None,
                         "last_passing_tau_s": max(passed) if passed else None})
    grid = [(i / (side + 1) * modes[0].lx_m, j / (side + 1) * modes[0].ly_m)
            for i in range(1, side + 1) for j in range(1, side + 1)]
    grids, resolutions = [], []
    for k in (1, 3):
        subset = modes[:k]
        vectors = [response(subset, [p]) for p in grid]
        collisions = passed = total = 0
        for i, a in enumerate(vectors):
            for b in vectors[i + 1:]:
                delta = [v - w for v, w in zip(a, b)]
                total += 1
                collisions += max(abs(v) for v in delta) <= 1e-10
                passed += comparison(delta, subset, selected, tau, gap, z)["passes_margin"]
        grids.append({"modes": k, "sites": len(grid), "pairs": total,
                      "exact_collisions_at_1e-10_hz": collisions, "pairs_passing_margin": passed,
                      "profile": selected.name, "tau_s": tau})
        for pos in grid:
            resolutions.append({"evidence_origin": "SIMULATED", "modes": k,
                                "x_nm": pos[0] * 1e9, "y_nm": pos[1] * 1e9,
                                **local_resolution(subset, pos, selected, tau)})
    xy = lambda x, y: (x * device["lx_m"], y * device["ly_m"])
    initial = positions_for(14, device["lx_m"], device["ly_m"])
    mirrored = [(device["lx_m"] - x, y) for x, y in initial]
    examples = []
    for name, a, b in [("swapped_xy_one_atom", [xy(.2, .3)], [xy(.3, .2)]),
                        ("mirror_x_one_atom", [xy(.2, .3)], [xy(.8, .3)]),
                        ("nearby_1nm_one_atom", [xy(.2, .3)], [xy(.2 + 1e-9 / device["lx_m"], .3)]),
                        ("mirror_x_14_atoms", initial, mirrored)]:
        for k in (1, 3):
            av, bv = response(modes[:k], a), response(modes[:k], b)
            examples.append({"name": name, "modes": k, "count": len(a),
                             "response_a_hz": av, "response_b_hz": bv,
                             **comparison([v - w for v, w in zip(av, bv)], modes[:k], selected, tau, gap, z)})
    reference = {str(n): shifts_from_weights(device["f11_hz"], device["effective_mass_kg"],
                                            [0.5] * n, limit) for n in (1, 14)}
    geo = config["geometry"]
    geometry = [geometry_budget(length, thickness, geo["density_kg_m3"],
                                geo["young_modulus_pa"], geo["poisson_ratio"],
                                device["f11_hz"], device["tension_ratio_y"])
                for length in geo["lengths_m"] for thickness in geo["thicknesses_m"]]
    implied_thickness = 4 * device["effective_mass_kg"] / (geo["density_kg_m3"]
                                                          * device["lx_m"] * device["ly_m"])
    report = {"schema_version": 1, "concept_status": "CONCEPT_ONLY", "evidence_origin": "SIMULATED",
              "calculation_status": "CPU_MODEL_RUN", "hardware_status": HARDWARE_STATUS,
              "mass_model": "FROZEN_MODE_MASS_ONLY", "entropy_bits": None,
              "source_base_commit": "1a4db64271e06548bbc28b71ec2a230b210dd0bd",
              "constants": {"rb87_mass_u": RB87_MASS_U, "atomic_mass_kg": ATOMIC_MASS_KG,
                            "rb87_mass_kg": RB87_MASS_KG}, "config": config,
              "reference_weight_0_5": reference, "scan_rows": len(rows),
              "noise_scan_rows": len(noise_rows), "noise_grid_optima": best,
              "modes": [{"p": m.p, "q": m.q, "f_hz": m.frequency_hz,
                         "linewidth_hz": m.frequency_hz / m.quality_factor,
                         "amplitude_ringdown_s": m.quality_factor / (math.pi * m.frequency_hz)}
                        for m in modes],
              "grid_pair_comparison": grids, "pair_examples": examples,
              "geometry_scan_rows": len(geometry),
              "baseline_implied_sine_plate_thickness_m": implied_thickness,
              "baseline_implied_h_over_min_L": implied_thickness / min(device["lx_m"], device["ly_m"]),
              "local_resolution_rows": len(resolutions),
              "omitted_physics": ["surface_forces", "adsorption_stiffness", "stress_change",
                                  "diffusion", "desorption", "readout_backaction", "mode_mixing"],
              "notes": ["No independent 49-bit entropy or PUF security claim.",
                        "Grid comparison is finite pairwise screening, not global reconstruction.",
                        "Local Fisher bounds omit drift, calibration uncertainty and mirror ambiguity.",
                        "Quality factor does not determine frequency measurement uncertainty."]}
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "frequency_scan.csv", rows)
    write_csv(out_dir / "noise_scan.csv", noise_rows)
    write_csv(out_dir / "local_resolution.csv", resolutions)
    write_csv(out_dir / "geometry_scan.csv", geometry)
    # Hash exact input bytes on CLI, source file, and every CSV for auditability.
    report["source_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report["output_sha256"] = {
        name: hashlib.sha256((out_dir / name).read_bytes()).hexdigest()
        for name in ("frequency_scan.csv", "geometry_scan.csv", "local_resolution.csv", "noise_scan.csv")
    }
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                                  allow_nan=False) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/rb14_phase1.json"))
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        config["input_sha256"] = hashlib.sha256(args.config.read_bytes()).hexdigest()
        report = run(config, args.out_dir)
    except (ValueError, KeyError, TypeError, StopIteration, OverflowError) as exc:
        parser.error(str(exc) or "invalid configuration")
    print(json.dumps({key: report[key] for key in ("concept_status", "evidence_origin",
                      "calculation_status", "scan_rows", "noise_scan_rows")}, allow_nan=False))


if __name__ == "__main__":
    main()
