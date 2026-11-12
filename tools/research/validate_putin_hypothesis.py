#!/usr/bin/env python3
"""Validate archival references and coverage; never score psychological accuracy."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path
import re
from urllib.parse import urlparse


DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "docs/research/putin_hypothesis"


def validate(root: Path) -> dict:
    def read(name: str) -> dict:
        return json.loads((root / "data" / name).read_text(encoding="utf-8"))

    errors: list[str] = []
    sources = read("sources.json")["sources"]
    claims = read("claims.json")["claims"]
    tasks = read("tasks.json")["tasks"]
    inventory = read("inventories.json")
    source_ids = {item["id"] for item in sources}
    allowed_statuses = {
        "page_read", "selected_passages_read", "metadata_read",
        "indexed_text_read", "indexed_excerpt_read", "api_metadata_read",
        "abstract_read",
    }
    for label, items in (("source", sources), ("claim", claims), ("task", tasks)):
        counts = Counter(item["id"] for item in items)
        errors.extend(f"duplicate {label} ID: {key}" for key, n in counts.items() if n > 1)
    for source in sources:
        if source["access_status"] not in allowed_statuses:
            errors.append(f"invalid access status: {source['id']}")
        parsed = urlparse(source["url"])
        if parsed.scheme != "https" or not parsed.netloc:
            errors.append(f"invalid source URL: {source['id']}")
        date.fromisoformat(source["checked_on"])
        for key in ("locator", "scope_note", "provenance_group"):
            if not source.get(key):
                errors.append(f"missing {key}: {source['id']}")
    for label, items, field in (
        ("claim", claims, "source_ids"),
        ("task", tasks, "answer_key_source_ids"),
    ):
        for item in items:
            if not item.get(field):
                errors.append(f"missing evidence: {item['id']}")
            for ref in item.get(field, []):
                if ref not in source_ids:
                    errors.append(f"unknown source {ref} in {label} {item['id']}")
    for task in tasks:
        if task["status"] != "NOT_RUN":
            errors.append(f"unexpected executed-task claim: {task['id']}")
        for field in ("prediction", "confidence", "outcome", "score"):
            if task[field] is not None:
                errors.append(f"unrun task has {field}: {task['id']}")
    summaries = {}
    for key in ("cather_interviews", "ledger_items"):
        items = inventory[key]
        ids = [item["item_id"] for item in items]
        if len(ids) != len(set(ids)):
            errors.append(f"duplicate inventory item: {key}")
        for item in items:
            if item.get("http_status") != 200 or "error" in item:
                errors.append(f"failed inventory fetch: {key}/{item['item_id']}")
            if not re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", "")):
                errors.append(f"missing response hash: {key}/{item['item_id']}")
            if item["reading_status"] not in {
                "selected_passages_read", "machine_fetched_not_close_read"
            }:
                errors.append(f"invalid inventory reading status: {key}/{item['item_id']}")
        summaries[key] = {
            "items": len(items),
            "successful_fetches": sum(item.get("http_status") == 200 for item in items),
            "selected_passages_read": sum(
                item["reading_status"] == "selected_passages_read" for item in items
            ),
        }
    for key in ("ledger_root_source_id", "cather_root_source_id"):
        if inventory[key] not in source_ids:
            errors.append(f"unknown inventory root: {inventory[key]}")

    citation = re.compile(r"\[([CHFWP]\d{2})(?:[–-]([CHFWP]\d{2}))?\]")
    for path in sorted(root.rglob("*.md")):
        content = path.read_text(encoding="utf-8")
        for start, end in citation.findall(content):
            refs = [start]
            if end:
                if end[0] != start[0] or int(end[1:]) < int(start[1:]):
                    errors.append(f"invalid reference range: {path.name}: {start}–{end}")
                    continue
                refs = [f"{start[0]}{n:02}" for n in range(int(start[1:]), int(end[1:]) + 1)]
            for ref in refs:
                if ref not in source_ids:
                    errors.append(f"unknown Markdown reference: {path.name}: {ref}")
        for target in re.findall(r"\]\(([^)]+)\)", content):
            if not urlparse(target).scheme and not target.startswith("#"):
                if not (path.parent / target.split("#", 1)[0]).exists():
                    errors.append(f"missing local link: {path.name}: {target}")
    return {
        "schema_version": 1,
        "as_of": inventory["as_of"],
        "validation_status": "PASS" if not errors else "FAIL",
        "scope": "Offline reference integrity and collection retrieval metadata only; not historical truth or psychological validity.",
        "sources": len(sources),
        "source_access_statuses": dict(Counter(s["access_status"] for s in sources)),
        "claims": len(claims),
        "tasks_not_run": sum(t["status"] == "NOT_RUN" for t in tasks),
        "inventories": summaries,
        "psychological_experiment_status": "NOT_RUN",
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = validate(args.root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"FAIL: invalid research dataset: {exc}")
        return 1
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0 if report["validation_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
