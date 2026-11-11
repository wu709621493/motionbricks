#!/usr/bin/env python3
"""Read-only, offline validation of the Han River literature evidence table.

Python standard library only; ACCEPT means schema consistency, not ecological
safety or independent verification of a paper. See the dataset VALIDATION.md.
"""

import argparse
from collections import Counter
import csv
from decimal import Context, Decimal, DecimalException, Inexact, InvalidOperation, localcontext
import json
from pathlib import Path
import re
from urllib.parse import urlsplit


DEFAULT_CSV = Path(__file__).resolve().parents[1] / (
    "docs/data/han_river_pharmaceuticals/concentrations.csv"
)
FIELDS = (
    "record_id source_id publication_year sampling_period sampling_year site "
    "matrix analyte evidence_type qualifier value_ng_L reported_plus_minus_ng_L "
    "uncertainty_type lower_ng_L upper_ng_L reporting_bound_ng_L source_url "
    "locator notes"
).split()
NUMERIC = (
    "value_ng_L", "reported_plus_minus_ng_L", "lower_ng_L", "upper_ng_L",
    "reporting_bound_ng_L",
)
QUALIFIERS = {
    "measured_summary": "mean",
    "reported_nondetect": "less_than",
    "modeled_range_of_means": "range_of_means",
    "not_retrieved": "not_available",
}
MATRICES = {
    "mainstem_water", "tributary_water", "wastewater_influent",
    "wastewater_effluent", "river_and_creek_water_summary", "surface_water",
}
# Deliberately reviewed source contracts, not a live metadata lookup. New sources
# or newly verified years require a documented contract update, never inference.
SOURCES = {
    "S2": ("2021", "https://doi.org/10.1038/s41598-021-89028-3", "measured_summary"),
    "S3": ("2010", "https://doi.org/10.1016/j.scitotenv.2009.10.049", "reported_nondetect"),
    "S4": ("2018", "https://doi.org/10.1016/j.scitotenv.2018.03.248", "modeled_range_of_means"),
    "SEARCH_GAP": ("", "", "not_retrieved"),
}
PDE5 = {"sildenafil", "tadalafil", "vardenafil"}
IDENTITY = ("source_id", "sampling_period", "sampling_year", "site", "matrix", "analyte")
NUMBER = re.compile(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")


def is_source_url(value):
    """Syntax only: no network, credentials, fragments, or bare host URLs."""
    try:
        url = urlsplit(value)
        return bool(
            not re.search(r"\s|[\x00-\x1f\x7f]", value)
            and url.scheme == "https" and url.hostname and "." in url.hostname
            and url.username is None and url.password is None
            and url.port in (None, 443) and url.path not in ("", "/")
            and not url.fragment
        )
    except ValueError:
        return False


def validate_stream(stream):
    """Return JSON-compatible diagnostics; never mutate or impute input cells."""
    errors, warnings, rows = [], [], []
    counts = Counter()
    seen_ids, seen_keys = set(), set()
    hr4 = []
    unknown_years = 0

    def error(line, code, message):
        errors.append({"line": line, "code": code, "message": message})

    def warn(code, message):
        warnings.append({"code": code, "message": message})

    reader = csv.reader(stream, strict=True)
    try:
        header = next(reader, None)
        if header != FIELDS:
            error(1, "HEADER", "Expected exactly the 19 ordered fields (all concentrations ng/L).")
        else:
            for cells in reader:
                line = reader.line_num
                rows.append(cells)
                if len(cells) != len(FIELDS):
                    error(line, "ROW_WIDTH", f"Expected 19 cells, got {len(cells)}.")
                    continue
                row = dict(zip(FIELDS, cells))
                if any(v != v.strip() for v in cells):
                    error(line, "WHITESPACE", "Surrounding whitespace is not an unknown value.")
                for field in ("record_id", "source_id", "sampling_period", "site", "matrix",
                              "analyte", "evidence_type", "qualifier", "notes"):
                    if not row[field].strip():
                        error(line, "REQUIRED", f"{field} must be nonempty.")
                if not re.fullmatch(r"HAN-[0-9]{3,}", row["record_id"]):
                    error(line, "RECORD_ID", "Expected HAN- followed by at least three digits.")
                if row["record_id"] in seen_ids:
                    error(line, "DUPLICATE_ID", row["record_id"])
                seen_ids.add(row["record_id"])
                key = tuple(row[f] for f in IDENTITY)
                if key in seen_keys:
                    error(line, "DUPLICATE_EVIDENCE", "Same source/period/site/matrix/analyte, even with a new ID.")
                seen_keys.add(key)

                kind = row["evidence_type"]
                counts[kind] += 1
                if kind not in QUALIFIERS or row["qualifier"] != QUALIFIERS.get(kind):
                    error(line, "EVIDENCE_QUALIFIER", "Unrecognized or mismatched evidence/qualifier.")
                if row["matrix"] not in MATRICES:
                    error(line, "MATRIX", "Only reviewed water matrices in ng/L are supported.")
                for field in ("publication_year", "sampling_year"):
                    if row[field] and not re.fullmatch(r"[12][0-9]{3}", row[field]):
                        error(line, "YEAR", f"{field} must be blank or a four-digit year (1000-2999).")
                if (re.fullmatch(r"[12][0-9]{3}", row["sampling_year"])
                        and re.fullmatch(r"[12][0-9]{3}", row["publication_year"])
                        and row["sampling_year"] > row["publication_year"]):
                    error(line, "YEAR_ORDER", "Sampling year cannot follow publication year.")
                source = row["source_id"]
                contract = SOURCES.get(source)
                if contract is None:
                    error(line, "SOURCE_CONTRACT", "New source requires a reviewed source contract.")
                elif tuple(row[f] for f in ("publication_year", "source_url", "evidence_type")) != contract:
                    error(line, "SOURCE_CONTRACT", "Source year, URL or evidence type differs from reviewed contract.")
                if source in SOURCES and row["sampling_year"]:
                    error(line, "UNKNOWN_YEAR", "Current sources have no verified sampling year; do not infer one.")
                if kind in ("measured_summary", "reported_nondetect") and not row["sampling_year"]:
                    unknown_years += 1
                if kind == "not_retrieved":
                    if any(row[f] for f in ("publication_year", "source_url", "locator", "sampling_year")):
                        error(line, "GAP_PROVENANCE", "Search gaps are not observations or published measurements.")
                elif not is_source_url(row["source_url"]) or not row["locator"].strip():
                    error(line, "PROVENANCE", "A valid HTTPS source URL and nonempty locator are required.")

                numbers = {}
                for field in NUMERIC:
                    value = row[field]
                    if value:
                        try:
                            number = Decimal(value)
                            if not NUMBER.fullmatch(value) or not number.is_finite() or number < 0:
                                raise InvalidOperation
                            numbers[field] = number
                        except (InvalidOperation, ValueError):
                            error(line, "NUMBER", f"{field}: expected finite nonnegative number in ng/L, without units.")
                allowed = {
                    "measured_summary": {"value_ng_L", "reported_plus_minus_ng_L"},
                    "reported_nondetect": {"reporting_bound_ng_L"},
                    "modeled_range_of_means": {"lower_ng_L", "upper_ng_L"},
                    "not_retrieved": set(),
                }.get(kind, set())
                for field in NUMERIC:
                    if field not in allowed and row[field]:
                        error(line, "FORBIDDEN_VALUE", f"{field} must be blank for {kind}; zero is not blank.")
                required = {"measured_summary": ("value_ng_L",),
                            "modeled_range_of_means": ("lower_ng_L", "upper_ng_L")}.get(kind, ())
                for field in required:
                    if not row[field]:
                        error(line, "MISSING_VALUE", f"{field} is required for {kind}.")
                for field in ("value_ng_L", "reporting_bound_ng_L"):
                    if numbers.get(field) == 0:
                        error(line, "ZERO_VALUE", f"{field} must be positive; zero cannot encode a nondetect.")
                if "lower_ng_L" in numbers and "upper_ng_L" in numbers:
                    if numbers["lower_ng_L"] > numbers["upper_ng_L"]:
                        error(line, "RANGE_ORDER", "Model lower bound exceeds upper bound.")
                expected_uncertainty = ("not_defined_in_table_caption"
                                        if kind == "measured_summary" and row["reported_plus_minus_ng_L"] else "")
                if row["uncertainty_type"] != expected_uncertainty:
                    error(line, "UNCERTAINTY", "Keep the reported +/- type unknown; do not invent SD/SE.")
                if kind == "reported_nondetect" and not row["reporting_bound_ng_L"]:
                    warn("UNKNOWN_REPORTING_BOUND", f"{row['record_id']}: bound unknown; not zero or a LOQ.")

                # Keep known source matrices, analytes and scope from being silently reclassified.
                if source == "S2":
                    site = row["site"]
                    matrix = ("mainstem_water" if re.fullmatch(r"HR-[1-5]", site) else
                              "tributary_water" if re.fullmatch(r"STP[12]_tributary_(upstream|downstream)", site) else
                              "wastewater_influent" if re.fullmatch(r"STP[12]_influent", site) else
                              "wastewater_effluent" if re.fullmatch(r"STP[12]_effluent", site) else None)
                    if row["matrix"] != matrix or row["analyte"] not in PDE5:
                        error(line, "SOURCE_SCOPE", "S2 Table 1 site/matrix/PDE-5 analyte mismatch.")
                    if site == "HR-4" and kind == "measured_summary" and "value_ng_L" in numbers:
                        hr4.append((row["analyte"], numbers["value_ng_L"]))
                elif source == "S3":
                    if (row["site"] != "Han_River_and_effluent_dominated_creeks_aggregate"
                            or row["matrix"] != "river_and_creek_water_summary"
                            or row["analyte"] not in {"17beta_estradiol_E2", "17alpha_ethinylestradiol_EE2", "progesterone", "testosterone"}):
                        error(line, "SOURCE_SCOPE", "S3 is an aggregate nondetect, not a specific station measurement.")
                elif source == "S4":
                    if (row["site"] != "four_Seoul_STPs" or row["matrix"] not in {"wastewater_influent", "wastewater_effluent"}
                            or row["analyte"] not in {"estrone_E1", "17beta_estradiol_E2"}
                            or row["sampling_period"] != "not_applicable_model"):
                        error(line, "SOURCE_SCOPE", "S4 is a four-STP model, not sampled river water.")
                elif source == "SEARCH_GAP":
                    if row["site"] != "Korean_Han_River" or row["matrix"] != "surface_water":
                        error(line, "SOURCE_SCOPE", "Search gaps describe the local review scope.")
    except csv.Error as exc:
        error(reader.line_num, "CSV_PARSE", str(exc))
    if not rows:
        error(1, "EMPTY_DATA", "At least one evidence record is required.")
    if unknown_years:
        warn("UNKNOWN_SAMPLING_YEAR", f"{unknown_years} observational summaries retain unknown sampling year.")
    warn("LOQ_NOT_ENCODED", "Schema has no analyte-specific LOQ field; reporting_bound_ng_L is not a LOQ.")
    warn("HR4_SOURCE_CONFLICT", "Unresolved historical S2 Table 1 HR-4: 5 + 2 + 2 = 9 ng/L versus prose <7 ng/L; do not repair source values.")
    hr4_sum = None
    if len(hr4) == 3 and {a for a, _ in hr4} == PDE5:
        try:
            with localcontext(Context(prec=28)) as context:
                context.traps[Inexact] = True
                hr4_sum = str(sum(v for _, v in hr4))
        except DecimalException:
            error(None, "ARITHMETIC_RANGE", "HR-4 values exceed decimal arithmetic capacity.")
    else:
        warn("HR4_SUM_UNAVAILABLE", "Input lacks exactly one valid mean per HR-4 PDE-5 analyte; historical conflict remains open.")
    return {"verdict": "DECLINE" if errors else "ACCEPT", "records": len(rows),
            "counts": dict(sorted(counts.items())), "hr4_sum_ng_L": hr4_sum,
            "errors": errors, "warnings": warnings}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", nargs="?", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--json", action="store_true", help="Print deterministic JSON diagnostics.")
    args = parser.parse_args(argv)
    try:
        with args.csv_path.open(encoding="utf-8-sig", newline="") as stream:
            result = validate_stream(stream)
    except (OSError, UnicodeError) as exc:
        result = {"verdict": "DECLINE", "records": 0, "counts": {}, "hr4_sum_ng_L": None,
                  "errors": [{"line": None, "code": "INPUT", "message": str(exc)}], "warnings": []}
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=True, sort_keys=True))
    else:
        print(f"{result['verdict']}: {result['records']} records; {len(result['errors'])} errors; {len(result['warnings'])} warnings")
        for kind, count in result["counts"].items():
            print(f"  {kind}: {count}")
        print(f"HR-4 input sum (ng/L): {result['hr4_sum_ng_L']}")
        for issue in result["errors"] + result["warnings"]:
            location = f"line {issue['line']}: " if issue.get("line") is not None else ""
            print(f"{issue['code']}: {location}{issue['message']}")
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
