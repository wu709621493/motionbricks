from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

import numpy as np
from motionbricks.rs72 import Aircraft, beam_case, gust_case
from tools.rs72_gust.audit_baseline import audit
from motionbricks.rs72_gust import (Case, coefficients, convergence, integrate,
                                  one_cos, run, simulate)


class BaselineAudit(unittest.TestCase):
    def test_independent_algebra_matches_archive_and_original_code(self):
        result = audit()
        self.assertEqual((result['case_count'], result['small_angle_count'],
                          result['cl_count'], result['strength_count']), (21, 8, 0, 2))
        self.assertEqual(len(result['unknown_slots']), 2)

    def test_strict_ratio_boundary_and_separate_lift_screen(self):
        for sign in (-1, 1):
            self.assertNotIn('small_angle_screen_exceeded', gust_case(100., sign*10.)['model_flags'])
            self.assertIn('small_angle_screen_exceeded',
                          gust_case(100., sign*math.nextafter(10., math.inf))['model_flags'])
        result = gust_case(100, 3, replace(Aircraft(), cl_max_screen=.3))
        self.assertEqual(result['model_flags'], ['assumed_lift_coefficient_screen_exceeded'])


class DynamicDesign(unittest.TestCase):
    def test_profile_endpoints_signed_peak_and_support(self):
        for sign in (-1, 1):
            c = Case(gust_peak_m_s=sign*3)
            for t in (-1, 0, .6, 2):
                self.assertEqual(one_cos(t, c), 0)
            self.assertAlmostEqual(one_cos(.3, c), sign*3)

    def test_ritz_integrals_independently_integrated(self):
        x = np.linspace(0, 1, 10001)
        phi = (6*x*x - 4*x**3 + x**4) / 3
        self.assertAlmostEqual(float(np.trapezoid(phi**2, x)), 104/405, places=7)
        self.assertAlmostEqual(float(np.trapezoid((4*(1-x)**2)**2, x)), 16/5, places=6)
        self.assertAlmostEqual(float(np.trapezoid(phi, x)), 2/5, places=7)

    def test_static_limit_matches_original_tip_and_root_moment(self):
        c = Case()
        _, _, k, _, gain = coefficients(c)
        eta = gain * c.gust_peak_m_s / k
        base, loaded = beam_case(1), gust_case(c.tas_m_s, c.gust_peak_m_s)
        self.assertAlmostEqual(eta, loaded['tip_deflection_m'] - base['tip_deflection_m'], places=12)
        self.assertAlmostEqual(4*91e6/12**2*eta,
                               loaded['root_moment_nm'] - base['root_moment_nm'], places=6)

    def test_zero_gust_and_signed_increment_symmetry(self):
        zero = simulate(Case(gust_peak_m_s=0))
        np.testing.assert_array_equal(zero[1], 0)
        self.assertIsNone(zero[4]['increment_amplification'])
        up, down = simulate(Case()), simulate(Case(gust_peak_m_s=-3))
        np.testing.assert_allclose(up[1], -down[1], atol=1e-14, rtol=1e-14)

    def test_forced_response_against_independent_duhamel_integral(self):
        c = Case()
        mass, damping, k, omega, gain = coefficients(c)
        zeta = damping / (2*math.sqrt(k*mass))
        wd = omega * math.sqrt(1-zeta*zeta)
        t, eta, *_ = simulate(c, refinement=1)
        for target in (.1, .3, .8, 1.2):
            index = int(np.argmin(abs(t-target)))
            tau = np.linspace(0, min(t[index], .6), 50001)
            force = gain * 1.5 * (1-np.cos(math.pi*100*tau/30))
            lag = t[index] - tau
            kernel = np.exp(-zeta*omega*lag)*np.sin(wd*lag)/(mass*wd)
            exact = float(np.trapezoid(force*kernel, tau))
            self.assertAlmostEqual(float(eta[index]), exact, delta=1e-8)

    def test_free_damped_motion_matches_analytic_solution_and_loses_energy(self):
        m, k, zeta = 2., 200., .02
        omega = math.sqrt(k/m)
        t = np.linspace(0, 4, 8001)
        y = integrate(t, m, 2*zeta*m*omega, k, lambda _: 0., (1., 0.))
        wd = omega*math.sqrt(1-zeta*zeta)
        exact = np.exp(-zeta*omega*t)*(np.cos(wd*t)+zeta*omega/wd*np.sin(wd*t))
        np.testing.assert_allclose(y[:,0], exact, atol=1e-8, rtol=1e-8)
        energy = .5*m*y[:,1]**2+.5*k*y[:,0]**2
        self.assertLess(float(np.diff(energy).max()), 1e-8)

    def test_undamped_free_energy_is_conserved(self):
        t = np.linspace(0, 4, 8001)
        y = integrate(t, 2., 0., 200., lambda _: 0., (1., 0.))
        energy = y[:,1]**2+100*y[:,0]**2
        self.assertLess(float(np.max(abs(energy/energy[0]-1))), 1e-8)

    def test_constant_force_equilibrium(self):
        y = integrate(np.linspace(0, 1, 1001), 2., 1., 200., lambda _: 10., (.05, 0.))
        np.testing.assert_allclose(y[:,0], .05, atol=1e-14)
        np.testing.assert_allclose(y[:,1], 0., atol=1e-14)

    def test_slow_gust_tracks_static_response(self):
        result = simulate(Case(gradient_m=1000.))
        error = np.max(abs(result[1]-result[3])) / np.max(abs(result[3]))
        self.assertLess(float(error), .005)

    def test_timestep_convergence_and_tail(self):
        _, result = convergence()
        self.assertEqual(result['numerics_status'], 'CONVERGED')

    def test_eight_old_out_of_model_cases_rejected(self):
        for v, u in ((70,-15),(70,-7.5),(70,7.5),(70,15),
                     (100,-15),(100,15),(130,-15),(130,15)):
            with self.subTest(v=v,u=u), self.assertRaises(ValueError):
                simulate(Case(tas_m_s=v,gust_peak_m_s=u))

    def test_invalid_scalars_limits_and_step_budget_rejected(self):
        for key in Case.__dataclass_fields__:
            for value in (float('nan'), float('inf'), True, '3'):
                with self.subTest(key=key,value=value), self.assertRaises(ValueError):
                    simulate(replace(Case(), **{key:value}))
        for change in ({'tas_m_s':0}, {'gradient_m':-1}, {'wing_half_mass_kg':0},
                       {'damping_ratio':0}, {'damping_ratio':-.1},
                       {'damping_ratio':.5}, {'gradient_m':1e-12}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                simulate(replace(Case(), **change))
        with self.assertRaises(ValueError):
            simulate(aircraft=replace(Aircraft(), cl_max_screen=.3))
        with self.assertRaises(ValueError):
            simulate(aircraft=replace(Aircraft(), elastic_modulus_pa=True))

    def test_invalid_grids_and_force_rejected(self):
        for grid in ([0,0], [1,0], [0,float('nan')], [[0,1]], [0]):
            with self.assertRaises(ValueError):
                integrate(grid, 1., 1., 1., lambda _: 0.)
        with self.assertRaises(ValueError):
            integrate([0,1], 1., 1., 1., lambda _: float('nan'))

    def test_nonrepresentable_derived_parameters_rejected(self):
        for case in (Case(gradient_m=1e308), Case(tas_m_s=1e-300),
                     Case(wing_half_mass_kg=1e-320)):
            with self.subTest(case=case), self.assertRaises(ValueError):
                simulate(case)
        with self.assertRaises(ValueError):
            simulate(aircraft=replace(Aircraft(), span_m=1e308))
        for t in (True, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                one_cos(t, Case())
        with self.assertRaises(ValueError):
            integrate([0,1], 1., 1., 1., lambda _: 0., (True, 0.))

    def test_strength_and_model_flags_preserved(self):
        result = simulate(aircraft=replace(Aircraft(), yield_screen_pa=90e6))[4]
        self.assertIn('yield', result['strength_flags'])
        self.assertIn('linear_elasticity_exceeded', result['model_flags'])
        self.assertFalse(result['airworthiness_demonstrated'])

    def test_existing_output_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            sentinel = Path(folder)/'keep.txt'
            sentinel.write_text('keep')
            with self.assertRaises(FileExistsError):
                run(folder)
            self.assertEqual(sentinel.read_text(), 'keep')

    def test_written_history_has_matching_hash_and_explicit_scope(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/'new'
            result = run(target, Case(gust_peak_m_s=0))
            self.assertEqual(result, json.loads((target/'report.json').read_text()))
            self.assertEqual(result['history_sha256'], hashlib.sha256((target/'history.csv').read_bytes()).hexdigest())
            self.assertEqual(result['convergence']['numerics_status'], 'CONVERGED')
            self.assertFalse(result['model']['parameters_calibrated'])
            self.assertFalse(result['flight_release'])
            self.assertEqual(len(result['unallocated_unknown_slots']), 2)

    def test_failed_history_write_does_not_publish_success_report(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/'failed'
            with patch('motionbricks.rs72_gust.np.savetxt', side_effect=OSError('simulated write failure')):
                with self.assertRaises(OSError):
                    run(target, Case(gust_peak_m_s=0))
            self.assertFalse((target/'report.json').exists())
            self.assertEqual(json.loads((target/'failure.json').read_text())['status'], 'FAILED')

    def test_cli_refuses_invalid_case_before_creating_output(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/'refused'
            result = subprocess.run([sys.executable, '-m', 'motionbricks.rs72_gust',
                                     '--tas', '70', '--gust', '7.5', '--out-dir', str(target)],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 1)
            self.assertIn('outside linear aerodynamic assumptions', result.stderr)
            self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()
