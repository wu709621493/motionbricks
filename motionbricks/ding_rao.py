"""Ding Rao: provenance-preserving narrative compensation for motion authoring.

Standard-library, opt-in research tool. Consumes explicit span annotations, not
unannotated classical Chinese. Ranks symbolic clip metadata; never creates poses
or treats historical longevity as a motor parameter or an optimization reward.
"""

from copy import deepcopy
import json
from pathlib import Path
from urllib.parse import urlparse

from motionbricks.zero_guard import divide


KINDS = {"action", "body_state", "stance", "relation", "affect"}
MODALITIES = {"depicted", "reported", "intended", "negated", "uncertain"}
AGENCIES = {"direct", "delegated", "unspecified"}
AGE_BASES = {"source_reported_unspecified", "nominal", "completed_years"}
RIGS = {"soma", "unitree_g1"}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _text(value, name):
    _require(isinstance(value, str) and bool(value.strip()), f"{name}: nonempty text required")


def _index(rows, name):
    _require(isinstance(rows, list), f"{name}: expected list")
    result = {}
    for row in rows:
        _require(isinstance(row, dict), f"{name}: expected object")
        _text(row.get("id"), f"{name}.id")
        _require(row["id"] not in result, f"{name}: duplicate id {row['id']}")
        result[row["id"]] = row
    return result


def validate_corpus(corpus):
    """Validate referential and annotation integrity, not historical truth.

    Offsets are Python Unicode code-point offsets [start, end), on the original
    text. No implicit normalization, subject inference or calendar conversion.
    """
    _require(isinstance(corpus, dict), "corpus: expected object")
    _require(type(corpus.get("schema_version")) is int and corpus["schema_version"] == 1,
             "unsupported schema_version")
    _text(corpus.get("scope"), "scope")
    sources = _index(corpus.get("sources"), "sources")
    subjects = _index(corpus.get("subjects"), "subjects")
    passages = _index(corpus.get("passages"), "passages")
    for source in sources.values():
        for key in ("work", "locator", "url", "accessed", "edition_note"):
            _text(source.get(key), f"source.{key}")
        url = urlparse(source["url"])
        _require(url.scheme == "https" and bool(url.netloc), "source requires HTTPS URL")
        _require(source.get("kind") in {"lyric", "official_history", "synthetic"}, "source.kind")
    for subject in subjects.values():
        _text(subject.get("label"), "subject.label")
        _require(subject.get("role") in {"lyric_speaker", "emperor", "other"}, "subject.role")
        if subject["role"] == "emperor":
            _text(subject.get("dynasty"), "subject.dynasty")
        _require(isinstance(subject.get("age_claims"), list), "age_claims: expected list")
        _text(subject.get("age_note"), "subject.age_note")
    annotation_ids = set()
    for passage in passages.values():
        _require(passage.get("source_id") in sources, "unknown passage source")
        _require(passage.get("focus_subject_id") in subjects, "unknown focus subject")
        for key in ("text", "time_label", "annotation_note"):
            _text(passage.get(key), f"passage.{key}")
        _require(passage.get("coverage") == "selected_excerpt", "coverage must be selected_excerpt")
        annotations = _index(passage.get("annotations"), "annotations")
        for event in annotations.values():
            _require(event["id"] not in annotation_ids, "annotation ids must be globally unique")
            annotation_ids.add(event["id"])
            start, end = event.get("start"), event.get("end")
            _require(type(start) is int and type(end) is int and
                     0 <= start < end <= len(passage["text"]), "invalid span")
            _require(passage["text"][start:end] == event.get("quote"), "span/quote mismatch")
            _require(event.get("kind") in KINDS, "unknown event kind")
            _require(event.get("modality") in MODALITIES, "unknown event modality")
            _require(event.get("agency") in AGENCIES, "unknown event agency")
            _require(event.get("actor_id") in subjects, "unknown event actor")
            _require(event.get("target_id") is None or event["target_id"] in subjects,
                     "unknown event target")
            for key in ("label", "interpretation"):
                _text(event.get(key), f"event.{key}")
            source_kind = sources[passage["source_id"]]["kind"]
            _require(not (source_kind == "official_history" and event["modality"] == "depicted"),
                     "official history must retain reported/uncertain status")
            _require(not (source_kind == "lyric" and event["modality"] == "reported"),
                     "lyric depiction is not a historical observation")
    for subject in subjects.values():
        for claim in subject["age_claims"]:
            _require(isinstance(claim, dict), "age claim: expected object")
            _require(type(claim.get("years")) is int and claim["years"] >= 0,
                     "age years: nonnegative integer required")
            _require(claim.get("basis") in AGE_BASES, "unknown age basis")
            passage = passages.get(claim.get("passage_id"))
            _require(passage is not None, "unknown age passage")
            _require(subject["role"] == "emperor" and
                     passage["focus_subject_id"] == subject["id"] and
                     sources[passage["source_id"]]["kind"] == "official_history",
                     "age claim must cite this emperor's history passage")
            _text(claim.get("quote"), "age.quote")
            _require(claim["quote"] in passage["text"], "age quote absent from passage")
    return sources, subjects, passages


def load_corpus(path):
    """Load local UTF-8 JSON. The algorithm never downloads source URLs."""
    corpus = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_corpus(corpus)
    return corpus


def _withheld_reasons(event, focus):
    reasons = []
    if event["kind"] != "action":
        reasons.append("not_an_action")
    if event["actor_id"] != focus:
        reasons.append("different_actor")
    if event["agency"] != "direct":
        reasons.append("not_direct_agency")
    if event["modality"] not in {"depicted", "reported"}:
        reasons.append(event["modality"])
    return reasons


def _brief(sources, passage):
    events = []
    # Text order is not elapsed time, and does not resolve causal relationships.
    for event in sorted(passage["annotations"], key=lambda e: (e["start"], e["end"], e["id"])):
        item = deepcopy(event)
        item["withheld_reasons"] = _withheld_reasons(event, passage["focus_subject_id"])
        events.append(item)
    return {
        "passage_id": passage["id"],
        "focus_subject_id": passage["focus_subject_id"],
        "source": deepcopy(sources[passage["source_id"]]),
        "text": passage["text"],
        "time_label": passage["time_label"],
        "events": events,
        "action_tags": sorted({e["label"] for e in events if not e["withheld_reasons"]}),
        "context_event_ids": [e["id"] for e in events if e["kind"] != "action"],
        "annotation_status": "curated_annotations_require_independent_review",
        "pose_status": "not_generated",
        "missing_motion_parameters": ["duration_s", "joint_poses", "contact_geometry", "force_limits"],
        "may_execute": False,
    }


def narrative_brief(corpus, passage_id):
    """Preserve actor, intention, state, relationship and evidence in a sidecar."""
    sources, _, passages = validate_corpus(corpus)
    if passage_id not in passages:
        raise ValueError(f"unknown passage: {passage_id}; annotate new text explicitly")
    return _brief(sources, passages[passage_id])


def rank_candidates(corpus, passage_id, candidates, *, rig):
    """Rank caller-labelled candidates by Jaccard overlap of direct action tags.

    Extra unsupported tags, wrong rigs and non-direct events cannot increase a
    candidate's rank. Age, affect and persistence are deliberately absent from
    the score. A tag match is metadata compatibility, not pose validation.
    """
    _require(rig in RIGS, "unknown rig")
    brief = narrative_brief(corpus, passage_id)
    catalog = _index(candidates, "candidates")
    wanted = set(brief["action_tags"])
    accepted, rejected = [], []
    for candidate in catalog.values():
        _require(candidate.get("rig") in RIGS, "candidate rig")
        tags = candidate.get("action_tags")
        _require(isinstance(tags, list) and bool(tags), "candidate tags must be a nonempty list")
        for tag in tags:
            _text(tag, "candidate tag")
        _require(len(set(tags)) == len(tags), "duplicate candidate tag")
        _text(candidate.get("annotation_note"), "candidate.annotation_note")
        tags = set(tags)
        reasons = []
        if not wanted:
            reasons.append("no_direct_action_evidence")
        if candidate["rig"] != rig:
            reasons.append("rig_mismatch")
        if tags - wanted:
            reasons.append("unsupported_action_tags")
        if reasons:
            rejected.append({"candidate_id": candidate["id"], "reasons": reasons})
            continue
        score = divide(len(tags & wanted), len(tags | wanted), policy="undefined")
        accepted.append({
            "candidate_id": candidate["id"], "score": score.value,
            "score_status": score.status, "matched_tags": sorted(tags),
            "uncovered_tags": sorted(wanted - tags),
            "evidence_ids": [e["id"] for e in brief["events"]
                             if not e["withheld_reasons"] and e["label"] in tags],
        })
    accepted.sort(key=lambda c: (-c["score"], c["candidate_id"]))
    rejected.sort(key=lambda c: c["candidate_id"])
    return {
        "status": "METADATA_MATCHES" if accepted else "ABSTAIN",
        "rig": rig, "brief": brief, "candidates": accepted, "rejected": rejected,
        "score_meaning": "symbolic_action_tag_jaccard_not_probability_or_quality",
        "may_execute": False,
    }


def history_report(corpus):
    """Join documented actions and age claims by person, retaining missingness.

    One person per row and per action group. Mentions are never exposure dose.
    Conflicting ages remain separate; a range spans claims, not uncertainty in
    a fitted statistical model. No longevity correlation or causal fit is run.
    """
    sources, subjects, passages = validate_corpus(corpus)
    rows = []
    for subject in subjects.values():
        if subject["role"] != "emperor":
            continue
        events = []
        for passage in passages.values():
            if (passage["focus_subject_id"] == subject["id"] and
                    sources[passage["source_id"]]["kind"] == "official_history"):
                for event in passage["annotations"]:
                    if not _withheld_reasons(event, subject["id"]):
                        events.append({"event_id": event["id"], "label": event["label"],
                                       "passage_id": passage["id"], "time_label": passage["time_label"]})
        claims = []
        for claim in subject["age_claims"]:
            passage = passages[claim["passage_id"]]
            claims.append({**deepcopy(claim), "source_id": passage["source_id"],
                           "url": sources[passage["source_id"]]["url"]})
        ranges = []
        for basis in sorted({c["basis"] for c in claims}):
            values = sorted({c["years"] for c in claims if c["basis"] == basis})
            ranges.append({"basis": basis, "minimum_claim": min(values),
                           "maximum_claim": max(values), "conflict": len(values) > 1})
        rows.append({"subject_id": subject["id"], "label": subject["label"],
                     "dynasty": subject["dynasty"], "age_claims": claims,
                     "age_ranges_by_basis": ranges, "age_note": subject["age_note"],
                     "age_status": "RECORDED" if claims else "MISSING_IN_SELECTED_EVIDENCE",
                     "direct_action_tags": sorted({e["label"] for e in events}),
                     "events": events, "death_cause": "not_coded"})
    rows.sort(key=lambda row: row["subject_id"])
    groups = []
    for tag in sorted({tag for row in rows for tag in row["direct_action_tags"]}):
        included = [row for row in rows if tag in row["direct_action_tags"]]
        groups.append({"action_tag": tag, "subjects": [row["subject_id"] for row in included],
                       "n_subjects": len(included),
                       "n_with_age_claim": sum(bool(row["age_claims"]) for row in included)})
    return {
        "scope": corpus["scope"], "n_emperors": len(rows),
        "n_with_age_claim": sum(bool(row["age_claims"]) for row in rows),
        "rows": rows, "action_groups": groups,
        "absence_means": "not_annotated_in_selected_evidence_not_behavior_absent",
        "association_status": "NOT_ESTIMATED_selected_nonrepresentative_examples",
        "causal_effect": None, "longevity_reward": None,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path, help="UTF-8 annotated corpus JSON")
    parser.add_argument("--passage", help="emit one narrative brief instead of history report")
    parser.add_argument("--catalog", type=Path, help="optional caller-labelled candidate JSON list")
    parser.add_argument("--rig", choices=sorted(RIGS), default="soma")
    args = parser.parse_args()
    if args.catalog and not args.passage:
        parser.error("--catalog requires --passage")
    try:
        corpus = load_corpus(args.corpus)
        if args.catalog:
            candidates = json.loads(args.catalog.read_text(encoding="utf-8"))
            result = rank_candidates(corpus, args.passage, candidates, rig=args.rig)
        elif args.passage:
            result = narrative_brief(corpus, args.passage)
        else:
            result = history_report(corpus)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
