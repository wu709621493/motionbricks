"""Uncalibrated, fixed-root, one-coordinate RS-72 gust experiment; CPU only.

Incremental elastic response about the existing static 1g state. No rigid-body
motion, aerodynamic feedback, unsteady lift, torsion, certification or release.
"""
from dataclasses import asdict, dataclass
import argparse
import hashlib
import json
import math
import numbers
from pathlib import Path
import platform

import numpy as np
from motionbricks.rs72 import Aircraft, beam_case, gust_case

MAX_STEPS = 200_000


def finite(value, label, positive=False):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Real):
        raise ValueError(f'{label}: real scalar required')
    if not math.isfinite(value) or (positive and value <= 0):
        raise ValueError(f'{label}: finite {"positive " if positive else ""}scalar required')


@dataclass(frozen=True)
class Case:
    tas_m_s: float = 100.
    gust_peak_m_s: float = 3.
    gradient_m: float = 30.
    wing_half_mass_kg: float = 1200.
    damping_ratio: float = .02

    def validate(self, aircraft):
        for key, value in asdict(self).items():
            finite(value, key, positive=key != 'gust_peak_m_s')
        if self.damping_ratio > .2:
            raise ValueError('prototype supports 0 < damping_ratio <= 0.2')
        for key, value in asdict(aircraft).items():
            finite(value, key, positive=True)
        aircraft.validate()
        # Entire 1-cos gust lies between these endpoints, including signed gusts.
        endpoints = [gust_case(self.tas_m_s, u, aircraft)
                     for u in (0., self.gust_peak_m_s)]
        if any(r['model_flags'] for r in endpoints):
            raise ValueError('gust/trim outside linear aerodynamic assumptions')


def _coefficients(case, aircraft):
    case.validate(aircraft)
    length = aircraft.span_m / 2
    mass = (104 / 405) * case.wing_half_mass_kg
    stiffness = (16 / 5) * aircraft.elastic_modulus_pa * aircraft.second_moment_m4 / length**3
    omega = math.sqrt(stiffness / mass)
    damping = 2 * case.damping_ratio * math.sqrt(stiffness * mass)
    force_per_gust = (.5 * aircraft.density_kg_m3 * case.tas_m_s *
                      aircraft.wing_area_m2 * aircraft.lift_slope_per_rad /
                      aircraft.span_m) * (2 / 5) * length
    for name, value in [('mass', mass), ('stiffness', stiffness),
                        ('omega', omega), ('damping', damping),
                        ('force_per_gust', force_per_gust)]:
        finite(value, name, positive=True)
    return mass, damping, stiffness, omega, force_per_gust


def coefficients(case, aircraft=Aircraft()):
    try:
        return _coefficients(case, aircraft)
    except ArithmeticError as exc:
        raise ValueError('non-representable derived coefficients') from exc


def _one_cos(t, case):
    duration = 2 * case.gradient_m / case.tas_m_s
    if t <= 0 or t >= duration:
        return 0.
    return .5 * case.gust_peak_m_s * (1 - math.cos(math.pi * case.tas_m_s * t / case.gradient_m))


def one_cos(t, case):
    finite(t, 'time')
    finite(case.gust_peak_m_s, 'gust peak')
    finite(case.tas_m_s, 'TAS', positive=True)
    finite(case.gradient_m, 'gradient', positive=True)
    try:
        duration = 2 * case.gradient_m / case.tas_m_s
        finite(duration, 'gust duration', positive=True)
        value = _one_cos(t, case)
        finite(value, 'gust')
        return value
    except ArithmeticError as exc:
        raise ValueError('non-representable gust profile') from exc


def integrate(time, mass, damping, stiffness, force, initial=(0., 0.)):
    """Classical RK4; force is evaluated at the stage times, not interpolated."""
    for name, value in [('mass', mass), ('damping', damping), ('stiffness', stiffness)]:
        finite(value, name, positive=name != 'damping')
    if damping < 0:
        raise ValueError('negative damping unsupported')
    time = np.asarray(time, dtype=float)
    if (time.ndim != 1 or len(time) < 2 or len(time) > MAX_STEPS + 1
            or not np.isfinite(time).all() or np.any(np.diff(time) <= 0)):
        raise ValueError('finite increasing time grid within step budget required')
    if len(initial) != 2:
        raise ValueError('displacement/velocity pair required')
    for value in initial:
        finite(value, 'initial state')
    y = np.asarray(initial, dtype=float)
    if y.shape != (2,) or not np.isfinite(y).all():
        raise ValueError('finite displacement/velocity pair required')
    history = np.empty((len(time), 2))
    history[0] = y

    def rhs(t, state):
        f = force(t)
        finite(f, 'force')
        return np.array([state[1], (f - damping * state[1] - stiffness * state[0]) / mass])

    for i in range(len(time) - 1):
        t, h = time[i], time[i + 1] - time[i]
        a = rhs(t, y)
        b = rhs(t + h / 2, y + h * a / 2)
        c = rhs(t + h / 2, y + h * b / 2)
        d = rhs(t + h, y + h * c)
        y = y + h * (a + 2*b + 2*c + d) / 6
        if not np.isfinite(y).all():
            raise ValueError('non-finite integration state')
        history[i + 1] = y
    return history


def _simulate(case, aircraft, refinement):
    if isinstance(refinement, bool) or not isinstance(refinement, int) or not 0 <= refinement <= 4:
        raise ValueError('refinement must be an integer in [0, 4]')
    mass, damping, stiffness, omega, gain = coefficients(case, aircraft)
    period = 2 * math.pi / omega
    duration = 2 * case.gradient_m / case.tas_m_s
    tail = max(10 * period, 5 / (case.damping_ratio * omega))
    dt = min(period / 100, duration / 200)
    for label, value in [('duration', duration), ('tail', tail), ('dt', dt)]:
        finite(value, label, positive=True)
    gust_steps, tail_steps = duration / dt, tail / dt
    for label, value in [('gust steps', gust_steps), ('tail steps', tail_steps)]:
        finite(value, label, positive=True)
        if value > MAX_STEPS:
            raise ValueError('step budget exceeded before allocation')
    n_gust = 2 * math.ceil(gust_steps / 2)
    n_tail = math.ceil(tail_steps)
    n_gust *= 2**refinement
    n_tail *= 2**refinement
    if n_gust + n_tail > MAX_STEPS:
        raise ValueError('step budget exceeded before allocation')
    time = np.concatenate((np.linspace(0, duration, n_gust + 1),
                           np.linspace(duration, duration + tail, n_tail + 1)[1:]))
    gust = np.array([_one_cos(float(t), case) for t in time])
    history = integrate(time, mass, damping, stiffness, lambda t: gain * _one_cos(t, case))
    eta, velocity = history.T
    base = beam_case(1., aircraft)
    length = aircraft.span_m / 2
    root_gain = 4 * aircraft.elastic_modulus_pa * aircraft.second_moment_m4 / length**2
    moment = base['root_moment_nm'] + root_gain * eta
    sigma = np.abs(moment) * aircraft.outer_fiber_m / aircraft.second_moment_m4
    tip = base['tip_deflection_m'] + eta
    static_eta = gain * gust / stiffness
    structure_flags = []
    if sigma.max() > aircraft.yield_screen_pa:
        structure_flags.append('yield')
    if 1.5 * sigma.max() > aircraft.ultimate_screen_pa:
        structure_flags.append('ultimate_1_5x_load')
    deformation_flags = []
    if np.abs(tip).max() > length * aircraft.deflection_fraction_screen:
        deformation_flags.append('elastic_deflection')
    peak = int(np.argmax(np.abs(eta)))
    static_peak = abs(gain * case.gust_peak_m_s / stiffness)
    # Free-decay displacement envelope from the final state, normalized to peak.
    wd = omega * math.sqrt(1 - case.damping_ratio**2)
    envelope = math.hypot(eta[-1], (velocity[-1] + case.damping_ratio * omega * eta[-1]) / wd)
    summary = {
        'case': asdict(case), 'modal_mass_kg': mass, 'modal_stiffness_n_m': stiffness,
        'frequency_hz': 1 / period, 'steps': len(time) - 1,
        'dt_max_s': float(np.diff(time).max()), 'gust_duration_s': duration,
        'tail_s': tail, 'peak_increment_m': float(abs(eta[peak])),
        'peak_time_s': float(time[peak]), 'static_peak_increment_m': static_peak,
        'increment_amplification': float(abs(eta[peak]) / static_peak) if static_peak else None,
        'peak_total_abs_tip_m': float(np.abs(tip).max()),
        'peak_total_abs_stress_mpa': float(sigma.max() / 1e6),
        'tail_envelope_fraction': float(envelope / abs(eta[peak])) if eta[peak] else 0.,
        'aerodynamic_flags': [], 'strength_flags': structure_flags,
        'model_flags': deformation_flags + (['linear_elasticity_exceeded'] if 'yield' in structure_flags else []),
        'physical_validation': 'UNVALIDATED_ASSUMED_PARAMETERS',
        'airworthiness_demonstrated': False, 'flight_release': False,
        'dynamic_fracture_assessed': False,
    }
    return time, eta, velocity, static_eta, summary


def simulate(case=Case(), aircraft=Aircraft(), refinement=0):
    try:
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            result = _simulate(case, aircraft, refinement)
            # Check scalars as well as the state; e.g. a finite input can overflow
            # during trial-stress recovery or initial static-load calculation.
            json.dumps(result[4], allow_nan=False)
            return result
    except ArithmeticError as exc:
        raise ValueError('non-representable derived dynamics') from exc


def convergence(case=Case(), aircraft=Aircraft()):
    runs = [simulate(case, aircraft, refinement=r) for r in (0, 1, 2)]
    comparisons = []
    for coarse, fine in zip(runs, runs[1:]):
        scale = max(fine[4]['peak_increment_m'], 1e-9)
        peak_error = abs(coarse[4]['peak_increment_m'] - fine[4]['peak_increment_m']) / scale
        waveform_error = float(np.max(np.abs(coarse[1] - fine[1][::2]))) / scale
        peak_time_error = abs(coarse[4]['peak_time_s'] - fine[4]['peak_time_s'])
        passed = (peak_error <= .005 and waveform_error <= .005 and
                  peak_time_error <= 2 * coarse[4]['dt_max_s'])
        comparisons.append({'peak_relative_error': peak_error,
                            'waveform_relative_error': waveform_error,
                            'peak_time_error_s': peak_time_error, 'passed': bool(passed)})
    passed = all(c['passed'] for c in comparisons) and runs[-1][4]['tail_envelope_fraction'] < .01
    return runs, {'comparisons': comparisons, 'tail_passed': runs[-1][4]['tail_envelope_fraction'] < .01,
                  'numerics_status': 'CONVERGED' if passed else 'NOT_CONVERGED'}


def run(out_dir, case=Case(), aircraft=Aircraft()):
    target = Path(out_dir)
    if target.exists():
        raise FileExistsError('output directory already exists')
    runs, check = convergence(case, aircraft)
    source_paths = [Path(__file__), Path(__file__).with_name('rs72.py')]
    report = {'schema_version': 1, 'status': 'ILLUSTRATIVE_CPU_EXPERIMENT', 'python': platform.python_version(),
              'numpy': np.__version__, 'platform': platform.platform(),
              'aircraft_assumptions': asdict(aircraft),
              'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths},
              'solver': {'name': 'RK4', 'peak_and_waveform_relative_tolerance': .005,
                         'tail_envelope_tolerance': .01, 'max_steps_per_run': MAX_STEPS},
              'model': {'fixed_root': True, 'elastic_coordinates': 1,
                        'rigid_body_motion': False, 'aerodynamic_feedback': False,
                        'unsteady_aerodynamics': False, 'parameters_calibrated': False},
              'results': [r[4] for r in runs], 'convergence': check,
              'unallocated_unknown_slots': [
                  {'id': 'U01', 'status': 'UNSPECIFIED', 'value': None},
                  {'id': 'U02', 'status': 'UNSPECIFIED', 'value': None}],
              'airworthiness_demonstrated': False, 'flight_release': False}
    json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    target.mkdir(parents=True, exist_ok=False)
    try:
        t, eta, velocity, static_eta, _ = runs[-1]
        history_path = target / 'history.csv'
        with history_path.open('x', encoding='utf-8') as handle:
            np.savetxt(handle, np.column_stack((t, eta, velocity, static_eta)),
                       delimiter=',', header='t_s,eta_dynamic_m,velocity_m_s,eta_static_m', comments='')
        report['history_sha256'] = hashlib.sha256(history_path.read_bytes()).hexdigest()
        # A report is published only after the complete history was written.
        with (target / 'report.json').open('x', encoding='utf-8') as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write('\n')
    except Exception as exc:
        (target / 'failure.json').write_text(json.dumps({'status': 'FAILED', 'error': str(exc)}), encoding='utf-8')
        raise
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', required=True)
    parser.add_argument('--tas', type=float, default=100.)
    parser.add_argument('--gust', type=float, default=3.)
    parser.add_argument('--gradient', type=float, default=30.)
    parser.add_argument('--half-mass', type=float, default=1200.)
    parser.add_argument('--damping', type=float, default=.02)
    args = parser.parse_args()
    try:
        result = run(args.out_dir, Case(args.tas, args.gust, args.gradient, args.half_mass, args.damping))
        print(json.dumps(result, indent=2, allow_nan=False))
        if result['convergence']['numerics_status'] != 'CONVERGED':
            raise SystemExit(2)
    except (ValueError, OSError, OverflowError) as exc:
        parser.exit(1, f'RS-72 dynamic experiment refused: {exc}\n')
