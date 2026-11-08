"""Two separate, uncalibrated fields: dermal fluid proxy and idealized vortex.

No clinical inference, weather forecast, or physical DIMM/GPU claim. The renderer
reuses PR #50's CPU block transforms and Z-buffer; field equations use NumPy.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import platform

import numpy as np


def positive(value, name, *, zero=False):
    if not math.isfinite(value) or (value < 0 if zero else value <= 0):
        raise ValueError(f"{name} must be finite and {'nonnegative' if zero else 'positive'}")


@dataclass(frozen=True)
class SkinConfig:
    cells: int = 64
    width_mm: float = 40.0
    diffusivity_mm2_s: float = 0.002
    source_mm_s: float = 0.0015
    source_decay_s: float = 600.0
    drainage_s: float = 1800.0
    duration_s: float = 1800.0
    dt_s: float = 5.0

    def validate(self):
        if type(self.cells) is not int or not 16 <= self.cells <= 128:
            raise ValueError('cells must be an integer in [16, 128]')
        for name, value in asdict(self).items():
            positive(value, name, zero=name in ('diffusivity_mm2_s', 'source_mm_s', 'duration_s'))
        if self.duration_s > 3600 or math.ceil(self.duration_s / self.dt_s) > 10000:
            raise ValueError('duration limited to 3600 s and 10000 steps')
        dx = self.width_mm / self.cells
        if self.dt_s * (4 * self.diffusivity_mm2_s / dx**2 + 1 / self.drainage_s) > 1:
            raise ValueError('explicit diffusion/drainage positivity limit exceeded')


def laplacian_no_flux(field, dx):
    """Cell-centred five-point stencil; duplicated edge cells impose zero flux."""
    a = np.pad(field, 1, mode='edge')
    return (a[1:-1, 2:] + a[1:-1, :-2] + a[2:, 1:-1]
            + a[:-2, 1:-1] - 4 * field) / dx**2


def skin_field(config=SkinConfig()):
    config.validate()
    n, dx = config.cells, config.width_mm / config.cells
    axis = (np.arange(n) + .5) * dx - config.width_mm / 2
    x, y = np.meshgrid(axis, axis)
    # Synthetic spatial permeability/source pattern; not histamine concentration.
    pattern = sum(weight * np.exp(-((x - cx)**2 + (y - cy)**2) / (2 * sigma**2))
                  for cx, cy, sigma, weight in ((-6, 3, 2.8, 1), (5, -4, 3.8, .85),
                                               (7, 7, 2.0, .65)))
    source = config.source_mm_s * pattern
    height = np.zeros((n, n), dtype=np.float64)
    history = [[0.0, 0.0, 0.0]]  # seconds, peak mm, equivalent fluid volume mm^3
    added = removed = 0.0
    t = 0.0
    for _ in range(math.ceil(config.duration_s / config.dt_s)):
        dt = min(config.dt_s, config.duration_s - t)
        influx = source * math.exp(-t / config.source_decay_s)
        outflux = height / config.drainage_s
        added += float(influx.sum()) * dx**2 * dt
        removed += float(outflux.sum()) * dx**2 * dt
        height = height + dt * (config.diffusivity_mm2_s * laplacian_no_flux(height, dx)
                                + influx - outflux)
        t += dt
        if not np.isfinite(height).all() or np.any(height < -1e-12):
            raise RuntimeError('nonfinite or negative fluid thickness')
        history.append([t, float(height.max()), float(height.sum()) * dx**2])
    volume = float(height.sum()) * dx**2
    residual = volume - (added - removed)
    if abs(residual) > 1e-9 * max(1.0, added):
        raise RuntimeError('no-flux global fluid balance failed')
    return {'axis_mm': axis, 'height_mm': height, 'history': np.array(history),
            'summary': {'peak_equivalent_thickness_mm': float(height.max()),
                        'equivalent_volume_mm3': volume, 'source_volume_mm3': added,
                        'drained_volume_mm3': removed, 'balance_residual_mm3': residual,
                        'dx_mm': dx, 'steps': len(history) - 1}}


@dataclass(frozen=True)
class VortexConfig:
    vmax_m_s: float = 45.0
    radius_max_m: float = 40000.0
    outer_radius_m: float = 300000.0
    outer_pressure_pa: float = 101000.0
    density_kg_m3: float = 1.2
    coriolis_s_inv: float = 5e-5
    half_width_m: float = 150000.0

    def validate(self):
        for name, value in asdict(self).items():
            positive(value, name, zero=name in ('vmax_m_s', 'coriolis_s_inv'))
        if not self.radius_max_m < self.outer_radius_m:
            raise ValueError('outer radius must exceed maximum-wind radius')
        if math.sqrt(2) * self.half_width_m > self.outer_radius_m:
            raise ValueError('square plotting domain exceeds pressure boundary radius')


def vortex_profile(radius_m, config=VortexConfig()):
    """Rankine tangential speed and pressure from cylindrical gradient balance.

    This is a boundary-layer-free, steady axisymmetric toy, not a 10 m wind
    observation. Finite outer pressure radius avoids the Coriolis log divergence.
    """
    config.validate()
    r = np.asarray(radius_m, dtype=np.float64)
    if not np.isfinite(r).all() or np.any(r < 0) or np.any(r > config.outer_radius_m):
        raise ValueError('radius must be finite and within the outer boundary')
    vmax, rm, ro = config.vmax_m_s, config.radius_max_m, config.outer_radius_m
    rho, f = config.density_kg_m3, config.coriolis_s_inv
    outside = np.maximum(r, rm)
    v = np.where(r <= rm, vmax * r / rm, vmax * rm / outside)
    deficit = rho * (.5 * vmax**2 * rm**2 * (1 / outside**2 - 1 / ro**2)
                     + f * vmax * rm * np.log(ro / outside))
    deficit += np.where(r < rm, .5 * rho * ((vmax / rm)**2 + f * vmax / rm)
                        * (rm**2 - r**2), 0.0)
    pressure = config.outer_pressure_pa - deficit
    if not np.isfinite(pressure).all() or np.any(pressure <= 0):
        raise ValueError('configuration implies invalid absolute pressure')
    return v, pressure


def vortex_field(cells=64, config=VortexConfig()):
    if type(cells) is not int or not 16 <= cells <= 128:
        raise ValueError('cells must be an integer in [16, 128]')
    config.validate()
    axis = (np.arange(cells) + .5) * (2 * config.half_width_m / cells) - config.half_width_m
    x, y = np.meshgrid(axis, axis)
    radius = np.hypot(x, y)
    speed, pressure = vortex_profile(radius, config)
    ratio = np.divide(speed, radius, out=np.zeros_like(speed), where=radius > 0)
    u, v = -ratio * y, ratio * x  # Northern Hemisphere, counterclockwise
    q = .5 * config.density_kg_m3 * speed**2
    return {'axis_m': axis, 'u_m_s': u, 'v_m_s': v, 'speed_m_s': speed,
            'pressure_pa': pressure, 'dynamic_pressure_pa': q}


def array_sha256(a):
    return hashlib.sha256(np.asarray(a, dtype='<f8').tobytes()).hexdigest()


def run(output_dir, cells=64):
    from motionbricks.memory_lab_worker import CpuBlockRuntime, host_info
    from motionbricks.wheal_typhoon_render import render

    skin_config = SkinConfig(cells=cells)
    skin_config.validate()
    storm_config = VortexConfig()
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=False)
    try:
        skin = skin_field(skin_config)
        storm = vortex_field(cells, storm_config)
        runtime = CpuBlockRuntime(4)
        drawing = render(target / 'comparison.png', skin, storm, runtime)
        # Radial momentum check uses a numerical pressure derivative, excluding
        # the piecewise-profile corner and origin; independently checked in tests.
        radii = np.array([10000., 20000., 60000., 100000., 200000.])
        vr, _ = vortex_profile(radii, storm_config)
        eps = 1.0
        dp = (vortex_profile(radii + eps, storm_config)[1]
              - vortex_profile(radii - eps, storm_config)[1]) / (2 * eps)
        acceleration = vr**2 / radii + storm_config.coriolis_s_inv * vr
        error = float(np.max(np.abs(dp / storm_config.density_kg_m3 - acceleration)))
        if error > 1e-9:
            raise RuntimeError('gradient-wind radial balance check failed')
        report = {'status': 'PASSED', 'meaning': 'numerical/render checks only; uncalibrated models',
                  'pr50': 'https://github.com/wu709621493/motionbricks/pull/50',
                  'host': host_info(), 'numpy_version': np.__version__,
                  'skin_config': asdict(skin_config), 'vortex_config': asdict(storm_config),
                  'skin': skin['summary'],
                  'vortex': {'analytic_vmax_m_s': storm_config.vmax_m_s,
                             'grid_max_speed_m_s': float(storm['speed_m_s'].max()),
                             'analytic_max_dynamic_pressure_pa': .5 * storm_config.density_kg_m3 * storm_config.vmax_m_s**2,
                             'analytic_central_pressure_pa': float(vortex_profile(0., storm_config)[1]),
                             'gradient_balance_max_error_m_s2': error,
                             'official_intensity_classification': None,
                             'wind_observation_height_m': None,
                             'wind_observation_average_minutes': None},
                  'field_hashes': {'skin_height_f64_le': array_sha256(skin['height_mm']),
                                   'vortex_speed_f64_le': array_sha256(storm['speed_m_s'])},
                  'rendering': drawing, 'pseudo_gpu': runtime.report(),
                  'clinical_validation': False, 'weather_forecast_validation': False,
                  'physical_dimms_tested': 0, 'supervised_memory_worker_used': False,
                  'python': platform.python_version()}
        with (target / 'report.json').open('x') as f:
            json.dump(report, f, indent=2, allow_nan=False)
            f.write('\n')
        return report
    except Exception as exc:
        with (target / 'failure.json').open('x') as f:
            json.dump({'status': 'FAILED', 'error': str(exc)}, f)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', required=True, help='new directory, never overwritten')
    parser.add_argument('--cells', type=int, default=64, choices=(32, 64, 96, 128))
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.out_dir, args.cells), indent=2, allow_nan=False))
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(1, f'wheal-typhoon failed: {exc}\n')


if __name__ == '__main__':
    main()
