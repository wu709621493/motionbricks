import copy
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('migration',Path(__file__).resolve().parents[1]/'tools/validate_china_migration.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class MigrationChecks(unittest.TestCase):
    def setUp(self):
        self.bundle=m.load_bundle()

    def test_accounting_and_provenance(self):
        self.assertEqual(m.validate(self.bundle)['observations'],177)

    def test_corrupt_source_rejected(self):
        self.bundle['observations'][0]['source_id']='invented'
        with self.assertRaisesRegex(ValueError,'Unknown observation source'):m.validate(self.bundle)

    def test_stock_flow_confusion_rejected(self):
        o=next(o for o in self.bundle['observations'] if o['measure_type']=='visa_issuance')
        o['unit']='persons'
        with self.assertRaisesRegex(ValueError,'Visa units'):m.validate(self.bundle)

    def test_margin_error_rejected(self):
        self.bundle['observations'][0]['count']+=1
        with self.assertRaisesRegex(ValueError,'Sex margin mismatch'):m.validate(self.bundle)

    def test_participant_data_rejected(self):
        self.bundle['observations'][0]['data_origin']='aou_participant'
        with self.assertRaisesRegex(ValueError,'Participant'):m.validate(self.bundle)

    def test_historical_overclaim_rejected(self):
        self.bundle['events'][0]['modern_exact_count']=700000
        with self.assertRaisesRegex(ValueError,'Historical quantities'):m.validate(self.bundle)

    def test_panel_cannot_assign_individual(self):
        self.bundle['panels'][0]['individual_assignment_allowed']=True
        with self.assertRaisesRegex(ValueError,'Panel cannot'):m.validate(self.bundle)

    def test_explicit_small_cell_boundary(self):
        r=m.direct_small_cell_check([0,1,19,20,21])
        self.assertEqual(r['unsafe_cell_indices'],[1,2,3])
        self.assertFalse(r['direct_count_threshold_pass'])

    def test_threshold_never_authorizes_release(self):
        r=m.direct_small_cell_check([0,21,100])
        self.assertTrue(r['direct_count_threshold_pass'])
        self.assertTrue(r['cross_table_disclosure_review_required'])
        self.assertFalse(r['release_authorized'])

    def test_invalid_counts_rejected(self):
        for counts in [[-1],[True],[1.5]]:
            with self.subTest(counts=counts),self.assertRaises(ValueError):m.direct_small_cell_check(counts)


if __name__=='__main__':unittest.main()
