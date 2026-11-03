"""Contract and counterexample tests; not an NLP or history accuracy benchmark."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import unittest

from motionbricks.ding_rao import history_report, load_corpus, narrative_brief, rank_candidates, validate_corpus


ROOT = Path(__file__).resolve().parents[2]


class DingRaoTests(unittest.TestCase):
    def setUp(self):
        self.corpus = load_corpus(ROOT / "data/ding_rao/seed.json")
        self.catalog = json.loads((ROOT / "data/ding_rao/demo_catalog.json").read_text(encoding="utf-8"))

    def passage(self, id):
        return next(p for p in self.corpus["passages"] if p["id"] == id)

    def test_couplet_preserves_story_without_inventing_a_motion(self):
        brief = narrative_brief(self.corpus, "poem_couplet")
        self.assertEqual(brief["action_tags"], [])
        self.assertEqual([e["kind"] for e in brief["events"]],
                         ["body_state", "stance", "relation", "body_state"])
        self.assertEqual(brief["events"][2]["target_id"], "beloved")
        self.assertFalse(brief["may_execute"])

    def test_full_poem_does_not_promote_intent_or_uncertainty(self):
        brief = narrative_brief(self.corpus, "poem_full")
        self.assertEqual(brief["action_tags"], ["look_far", "stand_lean"])
        events = {e["label"]: e for e in brief["events"]}
        self.assertIn("intended", events["drink"]["withheld_reasons"])
        self.assertIn("uncertain", events["sing"]["withheld_reasons"])
        self.assertNotIn("duration_s", brief)

    def test_delegation_does_not_make_emperor_a_machine_builder(self):
        brief = narrative_brief(self.corpus, "song_walk_order")
        self.assertEqual(brief["action_tags"], ["walk"])
        self.assertIn("not_direct_agency", brief["events"][1]["withheld_reasons"])
        self.assertIn("different_actor", brief["events"][1]["withheld_reasons"])

    def test_negated_action_is_not_a_candidate(self):
        # Synthetic counterexample annotation, not a claimed historical quotation.
        event = self.passage("song_walk_order")["annotations"][0]
        event["modality"] = "negated"
        self.assertEqual(narrative_brief(self.corpus, "song_walk_order")["action_tags"], [])

    def test_wrong_actor_is_excluded_even_when_action_is_reported(self):
        event = self.passage("tang_hunt")["annotations"][1]
        event["actor_id"] = "artisans"
        self.assertEqual(narrative_brief(self.corpus, "tang_hunt")["action_tags"], ["hunt"])

    def test_rank_has_independently_computable_scores_and_stable_ties(self):
        result = rank_candidates(self.corpus, "poem_full", self.catalog[::-1], rig="soma")
        self.assertEqual([(c["candidate_id"], c["score"]) for c in result["candidates"]],
                         [("demo_lean_and_look", 1.0), ("demo_lean_only", 0.5), ("demo_look_only", 0.5)])
        self.assertEqual(result["candidates"][1]["uncovered_tags"], ["look_far"])
        self.assertFalse(result["may_execute"])

    def test_partial_match_cannot_smuggle_in_unsupported_action(self):
        result = rank_candidates(self.corpus, "poem_full", self.catalog, rig="soma")
        rejected = {r["candidate_id"]: r["reasons"] for r in result["rejected"]}
        for id in ("demo_lean_and_drink", "demo_drink", "demo_loosen_belt"):
            self.assertIn("unsupported_action_tags", rejected[id])
        self.assertIn("rig_mismatch", rejected["demo_g1_lean"])

    def test_no_action_and_empty_catalog_abstain_without_zero_substitution(self):
        for passage, catalog in [("poem_couplet", self.catalog), ("poem_full", [])]:
            result = rank_candidates(self.corpus, passage, catalog, rig="soma")
            self.assertEqual(result["status"], "ABSTAIN")
            self.assertEqual(result["candidates"], [])

    def test_history_age_is_not_completed_years_and_missing_is_not_zero(self):
        report = history_report(self.corpus)
        self.assertEqual((report["n_emperors"], report["n_with_age_claim"]), (4, 3))
        rows = {r["subject_id"]: r for r in report["rows"]}
        self.assertEqual(rows["han_wudi"]["age_claims"], [])
        self.assertEqual(rows["tang_taizong"]["age_claims"][0]["years"], 52)
        self.assertEqual(rows["tang_taizong"]["age_claims"][0]["basis"], "source_reported_unspecified")
        self.assertIsNone(report["causal_effect"])
        self.assertIsNone(report["longevity_reward"])

    def test_age_changes_cannot_change_motion_ranking(self):
        catalog = [{"id": "synthetic_walk", "rig": "soma", "action_tags": ["walk"],
                    "annotation_note": "synthetic metadata"}]
        before = rank_candidates(self.corpus, "song_walk_order", catalog, rig="soma")
        subject = next(s for s in self.corpus["subjects"] if s["id"] == "song_taizu")
        subject["age_claims"] = []
        self.assertEqual(rank_candidates(self.corpus, "song_walk_order", catalog, rig="soma"), before)

    def test_duplicate_mentions_do_not_inflate_subject_count(self):
        duplicate = deepcopy(self.passage("song_hunt"))
        duplicate["id"] = "another_transcription"
        duplicate["annotations"][0]["id"] = "another_hunt_mention"
        self.corpus["passages"].append(duplicate)
        report = history_report(self.corpus)
        hunt = next(g for g in report["action_groups"] if g["action_tag"] == "hunt")
        self.assertEqual(hunt["n_subjects"], 3)
        self.assertEqual(report["n_emperors"], 4)

    def test_conflicting_age_claims_are_retained_and_not_averaged(self):
        p = deepcopy(self.passage("song_death"))
        p["id"] = "synthetic_conflicting_transcription"
        p["text"] = "年五十一"
        self.corpus["passages"].append(p)
        s = next(s for s in self.corpus["subjects"] if s["id"] == "song_taizu")
        s["age_claims"].append({"years": 51, "basis": "source_reported_unspecified",
                                "passage_id": p["id"], "quote": p["text"]})
        row = next(r for r in history_report(self.corpus)["rows"] if r["subject_id"] == s["id"])
        self.assertEqual(len(row["age_claims"]), 2)
        self.assertEqual(row["age_ranges_by_basis"][0],
                         {"basis": "source_reported_unspecified", "minimum_claim": 50,
                          "maximum_claim": 51, "conflict": True})

    def test_empty_historical_sample_reports_zero_people_not_zero_lifespan(self):
        self.corpus["subjects"] = []
        self.corpus["passages"] = []
        report = history_report(self.corpus)
        self.assertEqual((report["n_emperors"], report["rows"], report["action_groups"]), (0, [], []))

    def test_quote_and_span_must_still_match_after_text_edit(self):
        self.passage("poem_full")["text"] = "改" + self.passage("poem_full")["text"]
        with self.assertRaisesRegex(ValueError, "span/quote mismatch"):
            validate_corpus(self.corpus)

    def test_unknown_ids_and_duplicate_ids_are_rejected(self):
        for field in ("actor_id", "target_id"):
            bad = deepcopy(self.corpus)
            bad["passages"][0]["annotations"][0][field] = "unresolved"
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_corpus(bad)
        self.corpus["subjects"].append(deepcopy(self.corpus["subjects"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate id"):
            validate_corpus(self.corpus)

    def test_age_cannot_be_taken_from_another_person_or_unsourced_text(self):
        s = next(s for s in self.corpus["subjects"] if s["id"] == "song_taizu")
        s["age_claims"][0]["passage_id"] = "tang_death"
        with self.assertRaises(ValueError):
            validate_corpus(self.corpus)

    def test_invalid_numeric_age_is_not_silently_coerced(self):
        for value in (True, -1, 52.5, float("nan"), "52"):
            bad = deepcopy(self.corpus)
            next(s for s in bad["subjects"] if s["id"] == "tang_taizong")["age_claims"][0]["years"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_corpus(bad)

    def test_bad_catalogs_and_unknown_text_cannot_get_a_score(self):
        for catalog in ([self.catalog[0], self.catalog[0]],
                        [{**self.catalog[0], "action_tags": []}],
                        [{**self.catalog[0], "action_tags": ["stand_lean", "stand_lean"]}]):
            with self.subTest(catalog=catalog), self.assertRaises(ValueError):
                rank_candidates(self.corpus, "poem_full", catalog, rig="soma")
        with self.assertRaises(ValueError):
            narrative_brief(self.corpus, "new_unannotated_poem")

    def test_cli_runs_without_site_packages_and_keeps_json_machine_readable(self):
        proc = subprocess.run([sys.executable, "-S", "-m", "motionbricks.ding_rao",
                               "data/ding_rao/seed.json", "--passage", "poem_couplet"],
                              cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(proc.stdout)["action_tags"], [])

    def test_analysis_does_not_mutate_corpus_and_returns_detached_events(self):
        before = deepcopy(self.corpus)
        brief = narrative_brief(self.corpus, "poem_full")
        brief["events"][0]["label"] = "mutated"
        history_report(self.corpus)
        self.assertEqual(self.corpus, before)


if __name__ == "__main__":
    unittest.main()
