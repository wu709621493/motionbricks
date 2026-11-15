"""Independent consistency checks for the analytical source, standard library only."""

import math
import unittest
from fractions import Fraction as F

from model import C_LIGHT, G_NEWTON, STRESS_FACTOR as C, ParabolicBridge


class BridgeChecks(unittest.TestCase):
    def test_exact_rational_embedding_and_einstein_components(self):
        # Derive curvatures from r(z)=a+z^2/(4f), not from the stress formulas.
        # r' means d/dl, where dl/dz=sqrt(1+(dr/dz)^2).
        for a in (F(1), F(3, 2)):
            for f in (a/4, a/2, a, 2*a):
                for z in (F(0), F(1, 3), F(2)):
                    r = a+z*z/(4*f)
                    rz = z/(2*f)
                    rzz = 1/(2*f)
                    rp2 = rz*rz/(1+rz*rz)
                    rpp = rzz/(1+rz*rz)**2
                    kr = -rpp/r
                    kt = (1-rp2)/(r*r)
                    # Einstein tensor of ultrastatic warped geometry / (8piG/c^4).
                    expected = (2*kr+kt, -kt, -kr)
                    d = f+r-a
                    formula = (f*(f-a)/(r*r*d*d), -f/(r*r*d), f/(2*r*d*d))
                    self.assertEqual(expected, formula)
                    m = ParabolicBridge(float(a), float(f))
                    for actual, exact in zip(m.stresses(float(r)), expected):
                        self.assertAlmostEqual(actual/C, float(exact), places=13)

    def test_flare_out_and_no_horizon(self):
        for f in (0.1, 0.5, 1, 10):
            m = ParabolicBridge(1, f)
            self.assertEqual(m.shape(1), 1)
            self.assertLess(m.shape_prime(1), 1)
            self.assertLess(m.shape(1.1)/1.1, 1)
            # Phi=0 by construction; no claim about formation.

    def test_positive_density_still_violates_radial_nec(self):
        m = ParabolicBridge(1, 2)
        for r in (1, 1.1, 2, 10):
            self.assertGreater(m.stresses(r)[0], 0)
            self.assertLess(m.null_contraction(r, 1), 0)

    def test_angular_boundary(self):
        for f in (0.5, 1, 2):
            m = ParabolicBridge(1, f)
            for r in (1, 2, 5):
                mu2 = (r+2*f-2)/(3*r+2*f-2)
                self.assertAlmostEqual(m.null_contraction(r, math.sqrt(mu2))/C, 0, places=13)
                self.assertLess(m.null_contraction(r, 1), 0)
        self.assertLess(ParabolicBridge(1, 0.25).null_contraction(1, 0), 0)

    def test_stress_conservation_by_finite_difference(self):
        for f in (0.25, 1, 2):
            m = ParabolicBridge(1, f)
            for r in (1.2, 2, 4):
                h = r*1e-5
                derivative = (m.stresses(r+h)[1]-m.stresses(r-h)[1])/(2*h)
                _, pr, pt = m.stresses(r)
                self.assertLess(abs((derivative-2*(pt-pr)/r)/C), 2e-8)

    def test_volume_energy_by_regularized_simpson_quadrature(self):
        # Integrate in embedding z: no throat-coordinate singularity.
        for f in (0.25, 1, 2):
            m = ParabolicBridge(1, f)
            rmax = 4
            zmax = 2*math.sqrt(f*(rmax-1))
            n = 4000
            def integrand(z):
                r = 1+z*z/(4*f)
                dl_dz = math.sqrt(1+(z/(2*f))**2)
                return 8*math.pi*(m.stresses(r)[0]/C)*r*r*dl_dz
            h = zmax/n
            total = integrand(0)+integrand(zmax)
            total += sum((4 if i%2 else 2)*integrand(i*h) for i in range(1, n))
            self.assertAlmostEqual(total*h/3, m.proper_energy(rmax)/C, places=10)

    def test_point_limit_has_invariant_curvature_divergence(self):
        # K >= 4/a^4 independently of positive f, so a=0 has no regular limit.
        for a in (1, 0.1, 0.01):
            for f in (a/4, a, 10):
                m = ParabolicBridge(a, f)
                self.assertGreaterEqual(m.kretschmann(a), 4/a**4)
                self.assertAlmostEqual(m.kretschmann(a)/(2/(f*f*a*a)+4/a**4), 1)

    def test_length_and_stress_scaling(self):
        m = ParabolicBridge(1, 2)
        n = ParabolicBridge(3, 6)
        for left, right in zip(m.stresses(2), n.stresses(6)):
            self.assertAlmostEqual(left/(right*9), 1)
        self.assertAlmostEqual(n.kretschmann(6)/m.kretschmann(2), 3**-4)
        self.assertAlmostEqual(n.proper_energy(12)/m.proper_energy(4), 3)

    def test_schwarzschild_embedding_does_not_set_lapse(self):
        m = ParabolicBridge(1, 1)
        e, pr, pt = m.stresses(1)
        self.assertEqual(e, 0)
        self.assertLess(pr, 0)
        self.assertGreater(pt, 0)
        self.assertNotEqual(pr, 0)  # This ultrastatic spacetime is not vacuum Schwarzschild.

    def test_invalid_geometry_and_direction_refused(self):
        for a, f in ((0, 1), (1, 0), (-1, 1), (1, math.inf), (math.nan, 1)):
            with self.assertRaises(ValueError):
                ParabolicBridge(a, f)
        m = ParabolicBridge(1, 1)
        for r in (0, math.nan):
            with self.assertRaises(ValueError):
                m.stresses(r)
        with self.assertRaises(ValueError):
            m.null_contraction(1, 1.1)
        with self.assertRaises(ValueError):
            m.sample(count=10002)


if __name__ == "__main__":
    unittest.main(verbosity=2)
