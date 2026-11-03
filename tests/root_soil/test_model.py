import math
import unittest
from dataclasses import replace
from tools.root_soil.model import G, Plane, displacement, screen
from tools.root_soil.run_study import study


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.p = Plane('test', 25, 1, 1800, 3000, 32, 2000)

    def test_dry_cohesionless_analytic_angle_difference(self):
        p = replace(self.p, cohesion_pa=0, pore_pressure_pa=0)
        self.assertAlmostEqual(p.threshold()['critical_kh'], math.tan(math.radians(7)))

    def test_force_balance_at_yield(self):
        p = self.p
        k = p.threshold()['critical_kh']
        t = math.radians(p.slope_deg)
        n = p.weight_pa*(math.cos(t)-k*math.sin(t))-p.pore_pressure_pa
        resistance = p.cohesion_pa+n*math.tan(math.radians(p.friction_deg))
        self.assertAlmostEqual(resistance, p.weight_pa*(math.sin(t)+k*math.cos(t)))

    def test_area_scaling(self):
        a, b = self.p.threshold(), replace(self.p, area_m2=5).threshold()
        self.assertEqual(a['critical_kh'], b['critical_kh'])
        self.assertAlmostEqual(5*a['static_margin_n'], b['static_margin_n'])

    def test_moisture_and_root_direction(self):
        k = self.p.threshold()['critical_kh']
        self.assertGreater(replace(self.p, root_cohesion_pa=1000).threshold()['critical_kh'], k)
        self.assertLess(replace(self.p, pore_pressure_pa=4000).threshold()['critical_kh'], k)

    def test_subthreshold_no_motion(self):
        ay = self.p.threshold()['critical_kh']*G
        self.assertEqual(displacement(self.p, [ay*.99]*10, .1)['residual_displacement_m'], 0)

    def test_pulse_analytic_and_exact_stop(self):
        ay = self.p.threshold()['critical_kh']*G
        factor = math.cos(math.radians(25))+math.sin(math.radians(25))*math.tan(math.radians(32))
        # One second at twice yield, followed by one second at zero: equal acceleration/deceleration.
        expected = factor*ay
        for dt, n in ((1,1), (.1,10), (.01,100)):
            r = displacement(self.p, [2*ay]*n+[0]*n, dt)
            self.assertAlmostEqual(r['residual_displacement_m'], expected)
        r = displacement(self.p, [2*ay, 0, 0], 1)
        self.assertAlmostEqual(r['record_displacement_m'], expected)

    def test_post_record_runout(self):
        ay = self.p.threshold()['critical_kh']*G
        a = displacement(self.p, [2*ay], 1)
        b = displacement(self.p, [2*ay,0,0], 1)
        self.assertAlmostEqual(a['residual_displacement_m'], b['residual_displacement_m'])
        self.assertGreater(a['residual_displacement_m'], a['record_displacement_m'])

    def test_invalid_and_contact_limits(self):
        for kw in ({'thickness_m':0}, {'density_kg_m3':float('nan')}, {'root_cohesion_pa':-1},
                   {'pore_pressure_pa':1e8}, {'slope_deg':90}):
            with self.assertRaises(ValueError): replace(self.p, **kw)
        for record, dt in (([float('nan')], .1), ([100*G], .1), ([0], 0)):
            with self.assertRaises(ValueError): displacement(self.p, record, dt)
        huge = replace(self.p, root_cohesion_pa=1e8)
        self.assertIsNone(huge.threshold()['critical_kh'])
        self.assertEqual(screen([huge])['status'], 'incomplete')

    def test_static_failure_and_ties(self):
        p = replace(self.p, cohesion_pa=0, friction_deg=10)
        self.assertEqual(p.threshold()['status'], 'static_failure')
        with self.assertRaises(ValueError): displacement(p, [0], .1)
        self.assertEqual(screen([p, replace(p,label='second')])['weakest_candidates'], ['test','second'])
        with self.assertRaises(ValueError): screen([p,p])

    def test_deeper_bypass_and_study(self):
        p = self.p
        deep = replace(p, label='deep', thickness_m=2)
        result = screen([replace(p, root_cohesion_pa=6000), deep])
        self.assertEqual(result['weakest_candidates'], ['deep'])
        report = study()
        self.assertEqual(len(report['cases']), 12)
        self.assertEqual(report['evidence'], 'SYNTHETIC_UNCALIBRATED')

if __name__ == '__main__': unittest.main()
