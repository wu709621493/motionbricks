import unittest

from tools.ai_handoff.benchmark import CASES, POST_RELEASE, VALID, fixtures, run_case, study


class BenchmarkTests(unittest.TestCase):
    def test_all_fault_classes_are_exercised_without_budget_masking(self):
        expected = {
            "unit_error": "EVIDENCE_MISMATCH", "unknown_unit": "UNSUPPORTED_UNIT",
            "missing_coordinate": "SCHEMA_MISMATCH", "wrong_coordinate": "EVIDENCE_MISMATCH",
            "missing_source": "SCHEMA_MISMATCH", "wrong_source": "PROVENANCE_MISMATCH",
            "missing_model_version": "SCHEMA_MISMATCH", "conflicting_duplicate": "MESSAGE_ID_CONFLICT",
            "expired": "EXPIRED", "evidence_expired": "EXPIRED",
            "revision_changed": "STALE_REVISION", "withdrawn": "CANCELLED",
            "unauthorized_sender": "UNAUTHORIZED_SENDER",
            "unauthorized_operation": "UNAUTHORIZED_ROUTE_OR_OPERATION",
            "unauthorized_receiver": "UNAUTHORIZED_ACTOR", "unauthorized_release": "UNAUTHORIZED_ACTOR",
            "bad_conversion": "VERIFICATION_FAILED", "bad_receipt": "RECEIPT_MISMATCH",
            "withdraw_after_release": "CANCELLED", "revise_after_release": "STALE_REVISION",
            "expire_after_release": "EXPIRED",
        }
        self.assertEqual(set(expected) | VALID, set(CASES))
        for f in fixtures(per_case=3):
            for topology in ("broadcast", "directed"):
                with self.subTest(case=f["case"], topology=topology):
                    r = run_case(f, topology)
                    self.assertEqual(r["outcome"], "RELEASED" if f["case"] in VALID else expected[f["case"]])
                    self.assertFalse(r["unsafe_release"])
                    self.assertEqual(r["completed"], f["case"] in VALID)
                    if f["case"] in POST_RELEASE:
                        self.assertEqual((r["historical_releases"], r["invalidations"]), (1, 1))

    def test_paired_reproducibility_and_message_cost(self):
        a = study(per_case=2)
        self.assertEqual(a, study(per_case=2))
        broadcast, directed, tight_broadcast, tight_directed = a["groups"]
        self.assertEqual(broadcast["decision_error_rate"], 0)
        self.assertEqual(directed["decision_error_rate"], 0)
        self.assertEqual(broadcast["deliveries"], 4 * directed["deliveries"])
        self.assertEqual(broadcast["bytes"], 4 * directed["bytes"])
        self.assertGreater(broadcast["work"], directed["work"])
        self.assertEqual(tight_broadcast["completed_valid"], 0)
        self.assertGreater(tight_directed["completed_valid"], 0)
        self.assertEqual([r["task_id"] for r in broadcast["rows"]], [r["task_id"] for r in directed["rows"]])
        for group in a["groups"]:
            self.assertEqual(group["unsafe_releases"], 0)
            for r in group["rows"]:
                self.assertLessEqual(r["work"], group["max_work_per_task"])


if __name__ == "__main__":
    unittest.main()
