"""Reproducible offline demonstration; run from any working directory."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from motionbricks.ding_rao import history_report, load_corpus, rank_candidates


def run():
    corpus = load_corpus(ROOT / "data/ding_rao/seed.json")
    catalog = json.loads((ROOT / "data/ding_rao/demo_catalog.json").read_text(encoding="utf-8"))
    return {
        "algorithm": "丁饶算法 / Ding Rao v0.1",
        "catalog_status": "synthetic_metadata_no_motion_assets",
        "couplet": rank_candidates(corpus, "poem_couplet", catalog, rig="soma"),
        "whole_poem": rank_candidates(corpus, "poem_full", catalog, rig="soma"),
        "history": history_report(corpus),
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2, allow_nan=False))
