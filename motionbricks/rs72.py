"""Taiqiang RS-72: civil subsonic weather-aircraft concept screening.

Uniform-load cantilever + quasi-steady vertical gust + LEFM sensitivity only.
All geometry, material allowables and airfoil parameters are hypothetical inputs.
No full-airframe FEM, aeroelasticity, certification, or flight-envelope release.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path

import numpy as np

from motionbricks.wheal_typhoon import positive

G = 9.80665


@dataclass(frozen=True)
class Aircraft:
    mass_kg: float = 12000.0
    span_m: float = 24.0
    wing_area_m2: float = 70.0
    elastic_modulus_pa: float = 70e9
    second_moment_m4: float = .0013
    outer_fiber_m: float = .30
    yield_screen_pa: float = 250e6
    ultimate_screen_pa: float = 400e6
    fracture_screen_mpa_sqrt_m: float = 30.0
    crack_m: float = .002
    crack_geometry_factor: float = 1.12
    lift_slope_per_rad: float = 4.8
    cl_max_screen: float = 1.8
    density_kg_m3: float = 1.2
    deflection_fraction_screen: float = .05

    def validate(self):
        for name, value in asdict(self).items():
            positive(value, name)
        if self.ultimate_screen_pa < self.yield_screen_pa:
            raise ValueError('ultimate screening stress must not be below yield')


def relative_velocity(ground_m_s, wind_m_s):
    ground, wind = np.asarray(ground_m_s, dtype=float), np.asarray(wind_m_s, dtype=float)
    if ground.shape != (3,) or wind.shape != (3,) or not (np.isfinite(ground).all() and np.isfinite(wind).all()):
        raise ValueError('two finite 3D vectors required')
    return ground - wind


def beam_case(load_factor, aircraft=Aircraft()):
    aircraft.validate()
    if not math.isfinite(load_factor):
        raise ValueError('finite load factor required')
    half = aircraft.span_m / 2
    lift = load_factor * aircraft.mass_kg * G
    w = lift / aircraft.span_m
    rigidity = aircraft.elastic_modulus_pa * aircraft.second_moment_m4
    moment = w * half**2 / 2
    stress = abs(moment) * aircraft.outer_fiber_m / aircraft.second_moment_m4
    tip = w * half**4 / (8 * rigidity)
    k = aircraft.crack_geometry_factor * stress / 1e6 * math.sqrt(math.pi * aircraft.crack_m)
    # Maximum tensile-fibre magnitude, regardless of wing bending direction.
    critical = ((aircraft.fracture_screen_mpa_sqrt_m / (aircraft.crack_geometry_factor * stress / 1e6))**2
                / math.pi if stress else None)
    utilization = {'elastic_deflection': abs(tip) / (half * aircraft.deflection_fraction_screen),
                   'yield': stress / aircraft.yield_screen_pa,
                   'ultimate_1_5x_load': 1.5 * stress / aircraft.ultimate_screen_pa,
                   'fracture': k / aircraft.fracture_screen_mpa_sqrt_m}
    flags = [name for name, value in utilization.items() if value > 1]
    return {'n': load_factor, 'root_shear_n': lift / 2, 'root_moment_nm': moment,
            'tip_deflection_m': tip, 'elastic_trial_stress_mpa': stress / 1e6,
            'stress_intensity_mpa_sqrt_m': k, 'critical_crack_m': critical,
            'utilization': utilization, 'exceeded_screens': flags,
            'linear_elastic_applicable': stress <= aircraft.yield_screen_pa,
            'status': 'SCREEN_EXCEEDED' if flags else 'WITHIN_ASSUMED_SCREENS'}


def gust_case(tas_m_s, gust_m_s, aircraft=Aircraft()):
    """Frozen quasi-steady linear lift estimate, not a FAR/CS-25 gust solution."""
    aircraft.validate()
    positive(tas_m_s, 'TAS')
    if not math.isfinite(gust_m_s):
        raise ValueError('finite vertical gust required')
    rho, area = aircraft.density_kg_m3, aircraft.wing_area_m2
    q = .5 * rho * tas_m_s**2
    cl_trim = aircraft.mass_kg * G / (q * area)
    delta_cl = aircraft.lift_slope_per_rad * gust_m_s / tas_m_s
    delta_n = q * area * delta_cl / (aircraft.mass_kg * G)
    result = beam_case(1 + delta_n, aircraft)
    # The 0.1 ratio is a stated modelling screen, not an aircraft operating limit.
    model_flags = []
    if abs(gust_m_s / tas_m_s) > .1:
        model_flags.append('small_angle_screen_exceeded')
    if abs(cl_trim + delta_cl) > aircraft.cl_max_screen:
        model_flags.append('assumed_lift_coefficient_screen_exceeded')
    result.update({'tas_m_s': tas_m_s, 'vertical_gust_m_s': gust_m_s,
                   'dynamic_pressure_pa': q, 'delta_n': delta_n,
                   'cl_linear_trial': cl_trim + delta_cl, 'model_flags': model_flags,
                   'status': 'MODEL_OUTSIDE_ASSUMPTIONS' if model_flags else result['status']})
    return result


def wing_deflection(x_m, load_factor, aircraft=Aircraft()):
    aircraft.validate()
    x = np.asarray(x_m, dtype=float)
    length = aircraft.span_m / 2
    if not np.isfinite(x).all() or np.any(x < 0) or np.any(x > length) or not math.isfinite(load_factor):
        raise ValueError('finite beam coordinate in [0, half-span] and load factor required')
    w = load_factor * aircraft.mass_kg * G / aircraft.span_m
    return w * x**2 * (6*length**2 - 4*length*x + x**2) / (24*aircraft.elastic_modulus_pa*aircraft.second_moment_m4)


def run(output_dir):
    from motionbricks.rs72_render import render
    from motionbricks.memory_lab_worker import CpuBlockRuntime, host_info
    aircraft = Aircraft()
    cases = [gust_case(speed, gust, aircraft) for speed in (70., 100., 130.)
             for gust in (-15., -7.5, -3., 0., 3., 7.5, 15.)]
    report = {'name': '台强 RS-72 / Taiqiang RS-72',
              'status': 'CONCEPT_SCREENING_ONLY',
              'assumptions': asdict(aircraft), 'host': host_info(), 'numpy_version': np.__version__,
              'environment_scope': {'beaufort_max_inclusive': 12, 'reference_10m_max_m_s': 36.9,
                                    'converted_to_flight_altitude': False,
                                    'ambient_wind_is_not_vertical_gust': True},
              'baseline_1g': beam_case(1., aircraft), 'illustrative_2_5g': beam_case(2.5, aircraft),
              'gust_cases': cases,
              'case_counts': {key: sum(c['status'] == key for c in cases)
                              for key in ('WITHIN_ASSUMED_SCREENS', 'SCREEN_EXCEEDED', 'MODEL_OUTSIDE_ASSUMPTIONS')},
              'airworthiness_demonstrated': False, 'flight_release': False,
              'full_airframe_fem': False, 'dynamic_gust_analysis': False,
              'material_selection_validated': False, 'fatigue_life_cycles': None}
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=False)
    try:
        runtime = CpuBlockRuntime(4)
        report['rendering'] = render(target / 'rs72_concept.png', aircraft, cases, runtime)
        report['pseudo_gpu'] = runtime.report()
        with (target / 'report.json').open('x') as handle:
            json.dump(report, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write('\n')
        return report
    except Exception as exc:
        (target / 'failure.json').write_text(json.dumps({'status': 'FAILED', 'error': str(exc)}))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', required=True, help='new directory, never overwritten')
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.out_dir), indent=2, ensure_ascii=False, allow_nan=False))
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(1, f'RS-72 failed: {exc}\n')


if __name__ == '__main__':
    main()
