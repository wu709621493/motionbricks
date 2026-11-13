"""CPU benchmarks for PR #99's limiting examples, not dimension-changing physics.

Run from the repository root with Python -S. No fitted or measured data are used.
"""
from __future__ import annotations

import argparse
import json
import math


def scalar_benchmark(steps: int) -> dict:
    """RK4 for chi'' + chi = 0 on [0, 8], chi(0)=1, chi'(0)=0.

    Fixed Minkowski background, J=0, U=chi^2/2 in dimensionless units.
    This is a test-field limit; it does not solve Einstein's equations.
    """
    if type(steps) is not int or not 32 <= steps <= 20000:
        raise ValueError("steps must be an integer in [32, 20000]")
    h = 8 / steps
    x, p = 1.0, 0.0
    position_error = energy_error = 0.0
    for i in range(steps):
        k1x, k1p = p, -x
        k2x, k2p = p + h * k1p / 2, -(x + h * k1x / 2)
        k3x, k3p = p + h * k2p / 2, -(x + h * k2x / 2)
        k4x, k4p = p + h * k3p, -(x + h * k3x)
        x += h * (k1x + 2 * k2x + 2 * k3x + k4x) / 6
        p += h * (k1p + 2 * k2p + 2 * k3p + k4p) / 6
        position_error = max(position_error, abs(x - math.cos((i + 1) * h)))
        energy_error = max(energy_error, abs((x * x + p * p) / 2 - .5))
    return {"steps": steps, "end_time_dimensionless": 8,
            "max_position_error": position_error, "max_energy_error": energy_error}


def wall_state(tau: float) -> dict:
    """rho=R/R0, tau=ct/R0, E/(4*pi*sigma*R0^2)=rho^2*gamma-rho^3.

    gamma is evaluated from the analytic trajectory, avoiding 1-beta^2
    cancellation. Extremely large tau can still round beta to 1 in float64.
    """
    if isinstance(tau, bool) or not isinstance(tau, (int, float)) or not math.isfinite(tau) or abs(tau) > 100:
        raise ValueError("tau must be finite in [-100, 100]")
    rho = math.hypot(1, tau)
    return {"tau": tau, "rho": rho, "beta": tau / rho, "gamma": rho,
            "normalized_energy": rho * rho * rho - rho ** 3}


def report(steps: int = 4000) -> dict:
    scalar = scalar_benchmark(steps)
    walls = [wall_state(t) for t in (0, .25, 1, 2, 8, 100)]
    # Independent central differences test d rho / d tau = beta.
    h = 1e-4
    derivative_error = max(abs((wall_state(t + h)["rho"] - wall_state(t - h)["rho"]) / (2 * h)
                               - wall_state(t)["beta"]) for t in (0, .25, 1, 2, 8))
    # The barrier maximum is 2/3 of R0, not the zero-energy nucleation radius.
    energy = lambda rho: rho ** 2 - rho ** 3
    barrier = 2 / 3
    barrier_slope = (energy(barrier + h) - energy(barrier - h)) / (2 * h)
    # Log slope of a pure radial force at fixed coupling, not an experimental fit.
    dimensions = []
    for d in (2, 3, 4):
        r1, r2 = 1.0, 2.0
        f1, f2 = r1 ** (1 - d), r2 ** (1 - d)
        dimensions.append({"spatial_dimension": d,
                           "inferred_d_F": 1 - math.log(f2 / f1) / math.log(r2 / r1)})
    checks = {
        "scalar_position": scalar["max_position_error"] < 1e-8,
        "scalar_energy": scalar["max_energy_error"] < 1e-8,
        "wall_velocity_derivative": derivative_error < 1e-8,
        "wall_subluminal": all(0 <= row["beta"] < 1 for row in walls),
        "wall_energy": max(abs(row["normalized_energy"]) / row["rho"] ** 3 for row in walls) < 1e-12,
        "barrier_distinct_from_nucleation": abs(barrier_slope) < 2e-8 and energy(barrier) > energy(1),
        "gauss_force_slope": all(abs(row["inferred_d_F"] - row["spatial_dimension"]) < 1e-12 for row in dimensions),
    }
    return {"schema_version": 1, "evidence_origin": "NUMERICAL_LIMITING_EXAMPLES",
            "full_coupled_field_solver": "NOT_RUN", "dimension_change": "NOT_RUN",
            "experimental_fit": "NOT_RUN", "verdict": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks, "scalar": scalar, "wall": walls,
            "wall_max_derivative_error": derivative_error,
            "barrier_radius_over_R0": barrier, "gauss": dimensions}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=4000)
    args = parser.parse_args(argv)
    try:
        result = report(args.steps)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
