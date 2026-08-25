"""
LostinSriLanka -- the refresh pipeline.

Runs every stage from the current corpus to a rebuilt dashboard:

    corpus -> segment -> tag aspects -> score polarity -> aggregate -> dashboard

Deliberately NOT a live service
-------------------------------
This is a refreshable pipeline, not a server. You run it; it finishes; the
dashboard is a static file. A live service would need a machine kept running,
monitored and paid for, and would be a single point of failure on demo day.
A static rebuild cannot be "down".

If a scheduled refresh is wanted later, schedule this script -- the logic does
not change.

Safety: the previous outputs are snapshotted before anything is overwritten, so
a bad refresh is always recoverable.

Run with:  python scripts/10_refresh.py
"""
import json
import shutil
from datetime import datetime
from typing import Dict, Optional

import pandas as pd

from . import config as C
from .aggregate import build_tree, flat_scorecards
from .aspects import tag_corpus
from .polarity import score_corpus
from .segment import segment_corpus

SNAPSHOT_DIR = C.ROOT / "data" / "snapshots"
ARTIFACTS = [
    "segments.csv", "segments_tagged.csv", "segments_scored.csv",
    "hierarchy.json", "scorecards.csv", "reviews_clean.csv",
]


def snapshot(verbose: bool = True) -> Optional[str]:
    """Copy current outputs aside before they are replaced."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = SNAPSHOT_DIR / stamp
    dest.mkdir(parents=True, exist_ok=True)

    copied = 0
    for name in ARTIFACTS:
        src = C.DATA_PROCESSED / name
        if src.exists():
            shutil.copy2(src, dest / name)
            copied += 1

    if not copied:
        dest.rmdir()
        if verbose:
            print("  no previous outputs to snapshot (first run)")
        return None

    if verbose:
        print("  snapshot: {} files -> data/snapshots/{}".format(copied, stamp))
    return stamp


def run(rebuild_dashboard: bool = True, use_cache: bool = True,
        score_trained: bool = False, verbose: bool = True) -> Dict:
    started = datetime.now()
    print("\nLostinSriLanka -- refresh pipeline\n" + "=" * 60)

    print("\n[0/5] snapshot")
    snap = snapshot(verbose)

    corpus = pd.read_csv(C.CLEAN_REVIEWS_CSV)
    print("\n[1/5] corpus: {} reviews, {} destinations, {} districts".format(
        len(corpus), corpus["destination"].nunique(), corpus["district"].nunique()))
    if "source" in corpus.columns:
        for src, n in corpus["source"].value_counts().items():
            print("        {:<24} {}".format(src, n))

    print("\n[2/5] segmentation")
    seg = segment_corpus(corpus, verbose=verbose)
    seg.to_csv(C.DATA_PROCESSED / "segments.csv", index=False, encoding="utf-8")

    print("\n[3/5] aspect tagging")
    seg, tag_report = tag_corpus(seg, verbose=False)
    print("  matched >= 1 aspect: {} of {} usable segments ({}%)".format(
        tag_report["segments_with_aspect"], tag_report["segments_usable"],
        tag_report["coverage_pct"]))
    seg.to_csv(C.DATA_PROCESSED / "segments_tagged.csv", index=False, encoding="utf-8")

    print("\n[3b/5] model-based aspect tagging (embeddings)")
    try:
        from .aspects_model import ASPECT_PROMPTS, tag_corpus_model
        seg = tag_corpus_model(seg, verbose=False)
        for k in ASPECT_PROMPTS:
            seg["uAsp_" + k] = seg["asp_" + k] | seg["mAsp_" + k]
        seg["u_n_aspects"] = seg[["uAsp_" + k for k in ASPECT_PROMPTS]].sum(axis=1)
        print("  tagged segments: rules {} -> union {}".format(
            int((seg["n_aspects"] > 0).sum()), int((seg["u_n_aspects"] > 0).sum())))
    except ImportError:
        print("  sentence-transformers not installed -- using rules only")

    print("\n[4/5] polarity")
    seg = score_corpus(seg, use_transformer=True, use_cache=use_cache, verbose=verbose)
    seg.to_csv(C.DATA_PROCESSED / "segments_scored.csv", index=False, encoding="utf-8")

    # Method F: the locally trained model, scored per (segment, aspect).
    #
    # OFF by default. The model is not used to build the tree (it inverts 55% of
    # safety complaints -- see aggregate.build_tree), so scoring the whole corpus
    # with it costs about an hour of CPU per refresh and produces a column
    # nothing reads. Enable only when running the comparison deliberately.
    from .polarity import score_aspects_trained, trained_model_available
    if score_trained and trained_model_available():
        print("\n[4b/5] trained model (Method F, per-aspect)")
        by_aspect = score_aspects_trained(seg, verbose=verbose)
        if not by_aspect.empty:
            by_aspect.to_csv(C.DATA_PROCESSED / "polarity_by_aspect.csv",
                             index=False, encoding="utf-8")
            print("  {} (segment, aspect) verdicts".format(len(by_aspect)))
            print("  distribution: {}".format(
                by_aspect["pol_trained"].value_counts().to_dict()))
    else:
        print("\n[4b/5] no trained model yet -- run scripts/11_finetune.py")

    print("\n[5/5] aggregation")
    tree = build_tree(seg)
    with open(C.DATA_PROCESSED / "hierarchy.json", "w", encoding="utf-8") as fh:
        json.dump(tree, fh, indent=2, ensure_ascii=False)
    cards = flat_scorecards(tree)
    cards.to_csv(C.DATA_PROCESSED / "scorecards.csv", index=False, encoding="utf-8")
    print("  {} scorecards across {} destinations".format(
        len(cards), tree["coverage"]["n_destinations"]))

    if rebuild_dashboard:
        print("\n[+] dashboard")
        import subprocess
        import sys
        script = C.ROOT / "scripts" / "08_build_dashboard.py"
        subprocess.run([sys.executable, str(script)], check=True)

    elapsed = (datetime.now() - started).total_seconds()
    summary = {
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "elapsed_seconds": round(elapsed, 1),
        "snapshot": snap,
        "reviews": int(len(corpus)),
        "segments": int(len(seg)),
        "scorecards": int(len(cards)),
        "destinations": tree["coverage"]["n_destinations"],
        "districts": tree["coverage"]["n_districts"],
    }
    with open(C.REPORTS / "last_refresh.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)

    print("\n" + "=" * 60)
    print("refresh complete in {:.0f}s".format(elapsed))
    if snap:
        print("previous version recoverable from data/snapshots/{}".format(snap))
    return summary


if __name__ == "__main__":
    run()
