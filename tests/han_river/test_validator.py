"""CPU-only regression and decline tests; no network or MotionBricks imports."""

import copy
import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import validate_han_river_csv as validator


class ValidatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = validator.DEFAULT_CSV.read_bytes()
        cls.rows = list(csv.DictReader(io.StringIO(cls.original.decode("utf-8"))))

    def encode(self, rows=None, fields=None):
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=fields or validator.FIELDS)
        writer.writeheader()
        writer.writerows(self.rows if rows is None else rows)
        return stream.getvalue()

    def check(self, rows=None):
        return validator.validate_stream(io.StringIO(self.encode(rows)))

    def decline(self, code, index=0, **changes):
        rows = copy.deepcopy(self.rows)
        rows[index].update(changes)
        result = self.check(rows)
        self.assertEqual(result["verdict"], "DECLINE")
        self.assertIn(code, {e["code"] for e in result["errors"]})
        return result

    def test_main_snapshot_counts_and_arithmetic(self):
        result = self.check()
        self.assertEqual(result["verdict"], "ACCEPT")
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["records"], 49)
        self.assertEqual(result["counts"], {
            "measured_summary": 39, "reported_nondetect": 4,
            "modeled_range_of_means": 4, "not_retrieved": 2,
        })
        self.assertEqual(result["hr4_sum_ng_L"], "9")
        self.assertEqual({w["code"] for w in result["warnings"]}, {
            "UNKNOWN_SAMPLING_YEAR", "LOQ_NOT_ENCODED", "HR4_SOURCE_CONFLICT",
        })

    def test_read_only_and_deterministic(self):
        before = copy.deepcopy(self.rows)
        self.assertEqual(self.check(), self.check())
        self.assertEqual(self.rows, before)
        self.assertEqual(validator.DEFAULT_CSV.read_bytes(), self.original)
        self.assertTrue(all(r["sampling_year"] == "" for r in self.rows))

    def test_decline_headers(self):
        for fields in (validator.FIELDS[:-1], validator.FIELDS + ["unit"],
                       validator.FIELDS[::-1], ["record_id"] * 19,
                       [f.replace("ng_L", "ug_L") for f in validator.FIELDS]):
            with self.subTest(fields=fields):
                result = validator.validate_stream(io.StringIO(",".join(fields) + "\n"))
                self.assertIn("HEADER", {e["code"] for e in result["errors"]})

    def test_decline_empty_and_ragged_csv(self):
        for body in ("", ",".join(validator.FIELDS) + "\n", self.encode() + "\n",
                     self.encode() + "short,row\n", self.encode() + "," * 19 + "\n",
                     self.encode() + '"unterminated'):
            with self.subTest(tail=body[-30:]):
                self.assertEqual(validator.validate_stream(io.StringIO(body))["verdict"], "DECLINE")

    def test_decline_duplicate_ids_and_semantic_duplicates(self):
        rows = copy.deepcopy(self.rows)
        rows.append(copy.deepcopy(rows[0]))
        self.assertIn("DUPLICATE_ID", {e["code"] for e in self.check(rows)["errors"]})
        rows[-1].update(record_id="HAN-999", notes="Different notes", locator="Another page")
        self.assertIn("DUPLICATE_EVIDENCE", {e["code"] for e in self.check(rows)["errors"]})

    def test_decline_invalid_numbers(self):
        for field in validator.NUMERIC:
            index = {"lower_ng_L": 43, "upper_ng_L": 43, "reporting_bound_ng_L": 39}.get(field, 0)
            for value in ("-1", "NaN", "sNaN", "Infinity", "-Infinity", "<1", "1 ng/L", "1,000", "1_000", " 2 "):
                with self.subTest(field=field, value=value):
                    self.decline("NUMBER", index, **{field: value})

    def test_decline_zero_mean_and_nondetect_bound(self):
        self.decline("ZERO_VALUE", value_ng_L="0")
        self.decline("ZERO_VALUE", 39, reporting_bound_ng_L="0")

    def test_decline_nondetect_filled_zero_or_half_bound(self):
        for value in ("0", "0.5", "1"):
            with self.subTest(value=value):
                self.decline("FORBIDDEN_VALUE", 39, value_ng_L=value)

    def test_decline_model_as_measured_even_after_field_rewrite(self):
        self.decline("SOURCE_CONTRACT", 43, evidence_type="measured_summary",
                     qualifier="mean", lower_ng_L="", upper_ng_L="", value_ng_L="29.5")

    def test_decline_gap_as_nondetect(self):
        self.decline("SOURCE_CONTRACT", 47, evidence_type="reported_nondetect",
                     qualifier="less_than", reporting_bound_ng_L="1")

    def test_decline_all_cross_type_numeric_leakage(self):
        cases = [(0, "lower_ng_L"), (0, "reporting_bound_ng_L"),
                 (39, "reported_plus_minus_ng_L"), (39, "upper_ng_L"),
                 (43, "value_ng_L"), (43, "reporting_bound_ng_L")]
        cases.extend((47, field) for field in validator.NUMERIC)
        for index, field in cases:
            with self.subTest(index=index, field=field):
                self.decline("FORBIDDEN_VALUE", index, **{field: "0"})

    def test_decline_qualifiers_and_unknown_evidence(self):
        for index, qualifier in ((0, "less_than"), (39, "mean"), (43, "mean"), (47, "less_than")):
            self.decline("EVIDENCE_QUALIFIER", index, qualifier=qualifier)
        self.decline("EVIDENCE_QUALIFIER", evidence_type="measured_sample")

    def test_decline_missing_required_fields_and_values(self):
        for field in ("record_id", "sampling_period", "site", "analyte", "notes"):
            with self.subTest(field=field):
                self.decline("REQUIRED", **{field: ""})
        self.decline("MISSING_VALUE", value_ng_L="")
        self.decline("MISSING_VALUE", 43, lower_ng_L="")
        self.decline("MISSING_VALUE", 43, upper_ng_L="")

    def test_decline_source_loss_or_replacement(self):
        for url in ("", "https://doi.org/10.1234/other", "http://doi.org/10.1038/s41598-021-89028-3"):
            self.decline("SOURCE_CONTRACT", source_url=url)
        self.decline("PROVENANCE", locator="")
        self.decline("SOURCE_CONTRACT", source_id="S99")

    def test_url_syntax(self):
        self.assertTrue(validator.is_source_url(self.rows[0]["source_url"]))
        for url in ("javascript:alert(1)", "https://", "https://example.org", "https://example.org/a b",
                    "https://user:password@example.org/a", "https://example.org:bad/a", "https://[invalid/a"):
            with self.subTest(url=url):
                self.assertFalse(validator.is_source_url(url))

    def test_decline_year_imputation_or_invalid_year(self):
        self.decline("UNKNOWN_YEAR", sampling_year="2021")
        self.decline("UNKNOWN_YEAR", 43, sampling_year="2018")
        for year in ("0", "2026.0", "unknown", "999", "3000"):
            self.decline("YEAR", sampling_year=year)
        self.decline("YEAR_ORDER", sampling_year="2022")
        self.decline("SOURCE_CONTRACT", publication_year="2020")

    def test_decline_range_reversal(self):
        self.decline("RANGE_ORDER", 43, lower_ng_L="40", upper_ng_L="38.4")

    def test_decline_invented_uncertainty(self):
        self.decline("UNCERTAINTY", uncertainty_type="SD")
        self.decline("UNCERTAINTY", 39, uncertainty_type="SE")

    def test_decline_source_matrix_and_analyte_mismatches(self):
        self.decline("MATRIX", matrix="sediment_ng_g")
        self.decline("SOURCE_SCOPE", matrix="wastewater_influent")
        self.decline("SOURCE_SCOPE", analyte="Viagra")
        self.decline("SOURCE_SCOPE", 39, site="HR-1")
        self.decline("SOURCE_SCOPE", 43, matrix="mainstem_water")
        self.decline("SOURCE_SCOPE", 43, sampling_period="April field sampling")

    def test_decline_gap_with_fabricated_provenance(self):
        self.decline("GAP_PROVENANCE", 47, publication_year="2026", locator="Table 1")

    def test_unknown_bound_is_accepted_without_imputation(self):
        rows = copy.deepcopy(self.rows)
        rows[39]["reporting_bound_ng_L"] = ""
        result = self.check(rows)
        self.assertEqual(result["verdict"], "ACCEPT")
        self.assertIn("UNKNOWN_REPORTING_BOUND", {w["code"] for w in result["warnings"]})
        self.assertEqual(rows[39]["reporting_bound_ng_L"], "")

    def test_valid_scientific_notation_zero_uncertainty_and_equal_range(self):
        rows = copy.deepcopy(self.rows)
        rows[0].update(value_ng_L="2e0", reported_plus_minus_ng_L="0")
        rows[43].update(lower_ng_L="0", upper_ng_L="0")
        self.assertEqual(self.check(rows)["verdict"], "ACCEPT")

    def test_new_search_gap_is_allowed(self):
        rows = copy.deepcopy(self.rows)
        rows.append(dict(rows[47], record_id="HAN-050", analyte="norethisterone"))
        self.assertEqual(self.check(rows)["verdict"], "ACCEPT")

    def test_hr4_warning_survives_missing_or_changed_values(self):
        for rows in ([r for r in self.rows if r["site"] != "HR-4"], copy.deepcopy(self.rows)):
            if len(rows) == 49:
                rows[9]["value_ng_L"] = "1"
            result = self.check(rows)
            self.assertIn("HR4_SOURCE_CONFLICT", {w["code"] for w in result["warnings"]})
            self.assertIn(result["hr4_sum_ng_L"], (None, "5"))

    def test_decimal_overflow_declines_instead_of_crashing(self):
        for value in ("1e999999999", "1e-999999999", "1.12345678901234567890123456789012345"):
            with self.subTest(value=value):
                self.decline("ARITHMETIC_RANGE", 9, value_ng_L=value)

    def run_cli(self, *args, cwd=None):
        return subprocess.run([sys.executable, "-S", str(ROOT / "tools/validate_han_river_csv.py"), *args],
                              cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=10)

    def test_cli_accept_from_other_directory_and_no_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self.run_cli("--json", cwd=tmp)
            second = self.run_cli("--json", cwd=tmp)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(json.loads(first.stdout)["verdict"], "ACCEPT")
        self.assertEqual(validator.DEFAULT_CSV.read_bytes(), self.original)

    def test_cli_decline_bad_data_missing_file_and_encoding(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            rows = copy.deepcopy(self.rows)
            rows[39]["value_ng_L"] = "0"
            path.write_text(self.encode(rows), encoding="utf-8")
            for candidate in (path, Path(tmp) / "missing.csv"):
                result = self.run_cli(str(candidate), "--json")
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(json.loads(result.stdout)["verdict"], "DECLINE")
                self.assertNotIn("Traceback", result.stderr)
            path.write_bytes(b"\xff\xfeinvalid")
            result = self.run_cli(str(path), "--json")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)["errors"][0]["code"], "INPUT")

    def test_utf8_bom_and_crlf(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bom.csv"
            path.write_bytes(b"\xef\xbb\xbf" + self.encode().encode("utf-8"))
            result = self.run_cli(str(path), "--json")
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
