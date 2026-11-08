"""Conservation, independent analytical limits, and model boundary checks."""
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest

import numpy as np

from motionbricks.wheal_typhoon import (SkinConfig, VortexConfig, laplacian_no_flux,
                                        skin_field, vortex_field, vortex_profile, run)
from motionbricks.rs72 import (Aircraft, G, beam_case, gust_case, relative_velocity,
                              wing_deflection, run as run_aircraft)


class SkinTests(unittest.TestCase):
    def test_no_flux_conserves_integral(self):
        field = np.random.default_rng(72).uniform(size=(24, 24))
        self.assertAlmostEqual(float(laplacian_no_flux(field, .3).sum()), 0, places=10)

    def test_diffusion_converges_to_continuum_cosine(self):
        errors = []
        for n in (16, 32, 64):
            x = (np.arange(n)+.5)/n
            f = np.tile(np.cos(math.pi*x), (n, 1))
            errors.append(float(np.abs(laplacian_no_flux(f, 1/n)+math.pi**2*f).max()))
        self.assertGreater(errors[0]/errors[1], 3.9)
        self.assertGreater(errors[1]/errors[2], 3.9)

    def test_zero_source_stays_zero(self):
        result = skin_field(SkinConfig(source_mm_s=0, duration_s=50))
        self.assertEqual(float(result['height_mm'].max()), 0)
        self.assertEqual(result['summary']['balance_residual_mm3'], 0)

    def test_global_volume_converges_to_analytic_ode(self):
        base = SkinConfig(cells=32, duration_s=300)
        rate = skin_field(replace(base, duration_s=.1, dt_s=.1))['summary']['equivalent_volume_mm3']/.1
        exact = rate*(math.exp(-300/base.source_decay_s)-math.exp(-300/base.drainage_s)) / (1/base.drainage_s-1/base.source_decay_s)
        errors = [abs(skin_field(replace(base, dt_s=dt))['summary']['equivalent_volume_mm3']-exact)
                  for dt in (5, 2.5)]
        self.assertGreater(errors[0]/errors[1], 1.9)
        self.assertLess(errors[1]/exact, .005)

    def test_default_balance_positive_and_peak_decays(self):
        result = skin_field()
        self.assertGreaterEqual(float(result['height_mm'].min()), 0)
        self.assertLess(abs(result['summary']['balance_residual_mm3']), 1e-9)
        self.assertGreater(float(result['history'][:, 1].max()), float(result['height_mm'].max()))

    def test_invalid_or_unbounded_config_refused(self):
        for change in ({'dt_s':1000}, {'source_mm_s':float('nan')}, {'cells':True},
                       {'duration_s':4000}, {'dt_s':.001}, {'diffusivity_mm2_s':-1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                skin_field(replace(SkinConfig(), **change))


class VortexTests(unittest.TestCase):
    def test_origin_peak_and_inverse_radius(self):
        v, p = vortex_profile([0, 20000, 40000, 80000, 300000])
        np.testing.assert_allclose(v, [0, 22.5, 45, 22.5, 6])
        self.assertTrue(np.all(np.diff(p)>0))
        self.assertEqual(p[-1], 101000)

    def test_pressure_satisfies_radial_force_balance(self):
        c = VortexConfig()
        r = np.array([5000., 20000., 60000., 200000.])
        v, _ = vortex_profile(r)
        dp = (vortex_profile(r+1)[1]-vortex_profile(r-1)[1])/2
        np.testing.assert_allclose(dp/c.density_kg_m3, v*v/r+c.coriolis_s_inv*v, rtol=1e-7)

    def test_symmetry_direction_and_dynamic_pressure(self):
        f = vortex_field(32)
        np.testing.assert_allclose(f['u_m_s'], -f['u_m_s'][::-1, :])
        np.testing.assert_allclose(f['v_m_s'], -f['v_m_s'][:, ::-1])
        self.assertGreater(f['v_m_s'][16, -1], 0)
        np.testing.assert_allclose(f['dynamic_pressure_pa'], .6*(f['u_m_s']**2+f['v_m_s']**2))

    def test_zero_wind_gives_uniform_pressure(self):
        v, p = vortex_profile([0, 40000, 300000], replace(VortexConfig(), vmax_m_s=0))
        np.testing.assert_array_equal(v, 0)
        np.testing.assert_array_equal(p, 101000)

    def test_invalid_profiles_refused(self):
        for r in (-1, float('inf'), 300001):
            with self.assertRaises(ValueError):
                vortex_profile(r)
        with self.assertRaises(ValueError):
            vortex_field(config=replace(VortexConfig(), half_width_m=300000))


class AircraftTests(unittest.TestCase):
    def test_relative_velocity_is_galilean_invariant(self):
        base = relative_velocity([100, 20, 0], [30, -5, 0])
        np.testing.assert_array_equal(base, [70, 25, 0])
        np.testing.assert_array_equal(base, relative_velocity([110, 30, 10], [40, 5, 10]))

    def test_steady_headwind_does_not_change_fixed_tas_load(self):
        for wind in (0., 17.2, 32.7, 36.9):
            air = relative_velocity([100-wind, 0, 0], [-wind, 0, 0])
            self.assertEqual(gust_case(float(np.linalg.norm(air)), 0)['n'], 1)

    def test_root_loads_independently_integrated(self):
        a = Aircraft()
        x = np.linspace(0, a.span_m/2, 1001)
        load = np.full_like(x, 2.5*a.mass_kg*G/a.span_m)
        result = beam_case(2.5)
        self.assertAlmostEqual(result['root_shear_n'], float(np.trapezoid(load, x)))
        self.assertAlmostEqual(result['root_moment_nm'], float(np.trapezoid(load*x, x)))

    def test_beam_boundaries_and_stiffness_scaling(self):
        a = Aircraft()
        result = beam_case(2.5)
        d = wing_deflection([0, a.span_m/2], 2.5)
        self.assertEqual(d[0], 0)
        self.assertAlmostEqual(d[1], result['tip_deflection_m'])
        doubled_e = beam_case(2.5, replace(a, elastic_modulus_pa=2*a.elastic_modulus_pa))
        self.assertAlmostEqual(doubled_e['tip_deflection_m'], result['tip_deflection_m']/2)
        self.assertEqual(doubled_e['elastic_trial_stress_mpa'], result['elastic_trial_stress_mpa'])
        self.assertEqual(doubled_e['stress_intensity_mpa_sqrt_m'], result['stress_intensity_mpa_sqrt_m'])

    def test_toughness_and_crack_size_are_separate(self):
        base = beam_case(2.5)
        bigger_crack = beam_case(2.5, replace(Aircraft(), crack_m=.008))
        self.assertAlmostEqual(bigger_crack['stress_intensity_mpa_sqrt_m'], 2*base['stress_intensity_mpa_sqrt_m'])
        self.assertEqual(bigger_crack['tip_deflection_m'], base['tip_deflection_m'])
        tougher = beam_case(2.5, replace(Aircraft(), fracture_screen_mpa_sqrt_m=60))
        self.assertAlmostEqual(tougher['critical_crack_m'], 4*base['critical_crack_m'])

    def test_gust_symmetry_and_zero(self):
        up, down = gust_case(100, 3), gust_case(100, -3)
        self.assertAlmostEqual(up['n']+down['n'], 2)
        self.assertEqual(gust_case(100, 0)['delta_n'], 0)

    def test_large_gust_is_not_reported_as_pass(self):
        result = gust_case(100, 15)
        self.assertEqual(result['status'], 'MODEL_OUTSIDE_ASSUMPTIONS')
        self.assertIn('yield', result['exceeded_screens'])
        self.assertFalse(result['linear_elastic_applicable'])

    def test_signed_load_and_zero_load(self):
        up, down = beam_case(2), beam_case(-2)
        self.assertEqual(up['tip_deflection_m'], -down['tip_deflection_m'])
        self.assertEqual(up['stress_intensity_mpa_sqrt_m'], down['stress_intensity_mpa_sqrt_m'])
        self.assertIsNone(beam_case(0)['critical_crack_m'])

    def test_invalid_inputs_rejected(self):
        for call in (lambda: gust_case(0, 1), lambda: beam_case(float('nan')),
                     lambda: beam_case(1, replace(Aircraft(), crack_m=-1)),
                     lambda: relative_velocity([1, 2], [1, 2]), lambda: wing_deflection([13], 1)):
            with self.assertRaises(ValueError):
                call()


class IntegrationTests(unittest.TestCase):
    def test_rendered_evidence_and_exclusive_directories(self):
        with tempfile.TemporaryDirectory() as d:
            weather = run(Path(d)/'weather', cells=32)
            plane = run_aircraft(Path(d)/'plane')
            self.assertEqual(weather['rendering']['visible_field_meshes'], 2)
            self.assertGreater(weather['pseudo_gpu']['launches'], 0)
            self.assertFalse(plane['flight_release'])
            self.assertGreater(plane['case_counts']['MODEL_OUTSIDE_ASSUMPTIONS'], 0)
            for folder, data in (('weather', weather), ('plane', plane)):
                output = Path(d)/folder
                encoded = (output/data['rendering']['path']).read_bytes()
                self.assertTrue(encoded.startswith(b'\x89PNG\r\n\x1a\n'))
                self.assertEqual(hashlib.sha256(encoded).hexdigest(), data['rendering']['image_sha256'])
                self.assertEqual(json.loads((output/'report.json').read_text())['status'], data['status'])
            with self.assertRaises(FileExistsError):
                run(Path(d)/'weather', cells=32)
            with self.assertRaises(FileExistsError):
                run_aircraft(Path(d)/'plane')


if __name__ == '__main__':
    unittest.main()
