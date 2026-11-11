---
name: lay-eggs-xenopus
description: Validate the MotionBricks Han River pharmaceutical evidence CSV and develop source-grounded Xenopus amphibian ecological hypotheses. Use for "lay eggs! Xenopus!", Han River evidence audits, decline tests, or translating historical frog pregnancy assays into carefully bounded environmental research proposals. Do not use for personal pregnancy diagnosis or unrelated egg-laying questions.
---

# lay eggs! Xenopus!

## Establish the evidence base

1. Locate the MotionBricks repository root. Use repository-relative paths below; run commands from that root. Require Python 3.12 or newer, without installing MotionBricks or GPU dependencies.
2. Read the current [data dictionary](../../../docs/data/han_river_pharmaceuticals/README.md), [evidence CSV](../../../docs/data/han_river_pharmaceuticals/concentrations.csv), and [validation contract](../../../docs/data/han_river_pharmaceuticals/VALIDATION.md). Record the actual commit/ref and data digest. If remote access is unavailable, identify the local snapshot and avoid calling it latest main.
3. Read the [amphibian supplement](../../../docs/han_river_amphibians_xenopus_zh.md) for biological claims and sources. Consult the [conversation summary](../../../docs/han_river_xenopus_session_summary_zh.md) only for the original design decisions; prefer current source files over historical counts or earlier chat claims.

## Validate before interpreting

Run the existing standard-library implementation; do not duplicate it inside this skill:

```bash
python -S tools/validate_han_river_csv.py --json
python -S -m unittest discover -s tests/han_river -v
```

To audit a candidate table, pass its path explicitly:

```bash
python -S tools/validate_han_river_csv.py /absolute/path/to/candidate.csv --json
```

- Treat exit 0 / ACCEPT as structural consistency only; retain all warnings. Treat exit 1 / DECLINE as data or input failure. Report code, record/line when available, and required review; leave the supplied file unchanged.
- Keep measured summaries, nondetects, modeled ranges, and retrieval gaps separate. Never substitute zero, half a bound, a model mean, or a publication year for missing evidence.
- Keep `reporting_bound_ng_L` distinct from a verified analyte-specific LOD/LOQ. Preserve undefined +/- statistics and blank sampling years.
- Retain the historical HR-4 warning: S2 Table 1 reports 5 + 2 + 2 = 9 ng/L whereas the prose says <7. Report the current input sum separately; neither an edited sum nor missing rows resolves the original contradiction.
- Inspect source links and locators against primary literature when making new scientific claims. The offline checker does not resolve URLs, read papers, detect every numerical unit mislabel, or certify ecological safety.
- Add new sources or evidence forms only after updating the reviewed source contract, dictionary and meaningful decline tests. Use temporary copies for malformed fixtures. Do not silently change historical concentrations to make tests pass.

## Apply Xenopus without overstating the inference

1. Describe the 1934 Xenopus assay as an early animal pregnancy test, not the earliest pregnancy method. Separate hCG-driven ovulation from estrogen-receptor effects and PDE-5/cGMP pharmacology.
2. Label each statement as local exposure evidence, nonlocal experimental evidence, mechanistic hypothesis, or proposed test. Keep X. laevis, X. tropicalis and locally confirmed amphibian species distinct.
3. Use primary studies and official guidance. Record species, life stage, route, duration, chemical identity, measured versus nominal dose, controls and actual endpoint before comparing results. Do not import foreign laboratory doses into the local field CSV.
4. Treat a standardized hCG challenge as an optional reproductive-function proposal, not a pollutant identification test. Pair it conceptually with unstimulated endpoints; explain that external stimulation can mask natural-axis impairment. Never turn raw river-water injection into a generic hormone detector.
5. Start proposed follow-up with paired chemistry, receptor assays and local observations. If animal work is justified, refer to applicable ethical review and contained, standardized assays such as OECD TG 241; do not claim it measures the complete adult reproductive cycle or release Xenopus into the river.
6. State missing evidence plainly. Do not infer local population decline from a drug detection, a model estimate, a single biomarker, or a nonlocal experiment. Do not assume mixture synergy or a common ng/L potency scale.

## Deliver a reviewable result

Report scope/ref, ACCEPT or DECLINE, counts, diagnostics, exact commands and actual execution evidence. Distinguish this run from historical manual checks, historical CI, and pending paper/field verification. For requested edits, present a focused diff and source access limits; follow the user's authorization for PR creation and keep merge decisions separate.

Write the research summary in the user's requested language. Preserve the playful title while keeping evidence and uncertainty precise.
