import json
import math
import random
import subprocess
import sys
import unittest

from motionbricks.pigment_calcium import (
    CalciumPools, CalciumTransfers, gibbs_concentration_kj_mol,
    half_time_s, illustrative_report, photon_count, transfer_calcium,
)


class AccountingTests(unittest.TestCase):
    def test_photon_energy_and_scaling(self):
        self.assertAlmostEqual(photon_count(1, 300) / 1e15, 1.510234970262813)
        self.assertEqual(photon_count(0, 300), 0)
        self.assertAlmostEqual(photon_count(2, 300) / photon_count(1, 300), 2)
        self.assertAlmostEqual(photon_count(1, 600) / photon_count(1, 300), 2)

    def test_half_time_is_half_conversion(self):
        for rate in (.001, 3.8, 1e6):
            self.assertAlmostEqual(math.exp(-rate * half_time_s(rate)), .5)
        self.assertAlmostEqual(half_time_s(8.8e5, 1e-6), .7876672506363015)
        self.assertAlmostEqual(half_time_s(5.3e6, 2e-6) * 2, half_time_s(5.3e6, 1e-6))

    def test_gibbs_sign_and_reference(self):
        self.assertEqual(gibbs_concentration_kj_mol(310.15, 1), 0)
        self.assertAlmostEqual(gibbs_concentration_kj_mol(310.15, 10), 5.9377465946)
        self.assertAlmostEqual(gibbs_concentration_kj_mol(310.15, .1),
                               -gibbs_concentration_kj_mol(310.15, 10))

    def test_binding_and_release_are_not_loss(self):
        start = CalciumPools(10, 100, 0)
        bound = transfer_calcium(start, CalciumTransfers(pigment_bound_mg=4))
        self.assertEqual(bound.total_mg, start.total_mg)
        self.assertEqual(transfer_calcium(bound, CalciumTransfers(pigment_released_mg=4)), start)

    def test_export_is_loss_not_redistribution(self):
        start = CalciumPools(10, 100, 2)
        end = transfer_calcium(start, CalciumTransfers(pigment_exported_mg=2))
        self.assertEqual(end.total_mg, start.total_mg - 2)

    def test_random_feasible_ledgers_conserve_mass(self):
        rng = random.Random(701)
        for _ in range(200):
            p = CalciumPools(*(rng.uniform(1, 100) for _ in range(3)))
            t = CalciumTransfers(absorbed_mg=rng.random(), resorbed_mg=p.bone_mg*rng.random(),
                deposited_mg=p.circulating_mg*.2*rng.random(),
                pigment_bound_mg=p.circulating_mg*.2*rng.random(),
                pigment_released_mg=p.pigment_bound_mg*.4*rng.random(),
                excreted_mg=p.circulating_mg*.2*rng.random(),
                pigment_exported_mg=p.pigment_bound_mg*.4*rng.random())
            end = transfer_calcium(p,t)
            self.assertAlmostEqual(end.total_mg, p.total_mg+t.absorbed_mg-t.excreted_mg-t.pigment_exported_mg)

    def test_impossible_transfers_rejected_without_mutation(self):
        p = CalciumPools(1, 1, 1)
        for t in (CalciumTransfers(deposited_mg=.6, excreted_mg=.6),
                  CalciumTransfers(resorbed_mg=2),
                  CalciumTransfers(pigment_released_mg=.6, pigment_exported_mg=.6),
                  CalciumTransfers(absorbed_mg=10, excreted_mg=2)):
            with self.assertRaises(ValueError): transfer_calcium(p,t)
        self.assertEqual(p, CalciumPools(1,1,1))

    def test_invalid_numbers(self):
        for value in (-1, True, '1', None, float('nan'), float('inf')):
            for fn in (lambda: photon_count(value, 300), lambda: half_time_s(value),
                       lambda: gibbs_concentration_kj_mol(310.15,value),
                       lambda: CalciumPools(1,value,1), lambda: CalciumTransfers(absorbed_mg=value)):
                with self.assertRaises(ValueError): fn()
        for fn in (lambda: photon_count(1,0), lambda: half_time_s(0),
                   lambda: half_time_s(1,0), lambda: gibbs_concentration_kj_mol(0,1),
                   lambda: photon_count(1e308,1e308),lambda: half_time_s(1e-300,1e-300)):
            with self.assertRaises(ValueError): fn()

    def test_unknowns_stay_unknown_and_cli_needs_no_site_packages(self):
        r=illustrative_report()
        self.assertTrue(all(v is None for v in r['unidentified_outputs'].values()))
        self.assertAlmostEqual(r['synthetic_calcium_ledger']['conservation_residual_mg'],0)
        out=subprocess.run([sys.executable,'-S','-m','motionbricks.pigment_calcium'],
                           check=True,capture_output=True,text=True,timeout=10)
        self.assertEqual(json.loads(out.stdout),r)


if __name__ == '__main__': unittest.main()
