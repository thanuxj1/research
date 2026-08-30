"""
Guard test: storyboard media must never reach the calculations.

The claim "we only display this, we never count it" is worth nothing if it
lives only in a comment. These tests fail loudly if a future change wires the
media store into the aggregation.

Run:  python -m pytest tests/test_media_separation.py -q
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from travellens import aggregate, config as C, media  # noqa: E402


def test_aggregate_never_references_the_media_store():
    """No code path in aggregation may open media.csv or import media."""
    src = (ROOT / "src" / "travellens" / "aggregate.py").read_text(encoding="utf-8")
    assert "media.csv" not in src, "aggregate.py references the media store"
    assert "from .media" not in src and "import media" not in src, \
        "aggregate.py imports the media module"


def test_media_ids_cannot_collide_with_review_ids():
    """Media rows are keyed differently, so they cannot be merged in by accident."""
    assert "media_id" in media.MEDIA_COLUMNS
    assert "review_id" not in media.MEDIA_COLUMNS
    assert "segment_id" not in media.MEDIA_COLUMNS
    assert media.make_media_id("https://example.com/x").startswith("m_")


def test_tree_is_identical_with_and_without_media_present():
    """The strongest form of the guarantee: adding media changes no number."""
    seg_path = C.DATA_PROCESSED / "segments_scored.csv"
    if not seg_path.exists():
        return  # nothing built yet; nothing to assert
    seg = pd.read_csv(seg_path)
    before = aggregate.build_tree(seg)["aspects"]

    # Write a media row for a real destination, then rebuild.
    dest = seg["destination"].dropna().iloc[0]
    row = pd.DataFrame([{c: "" for c in media.MEDIA_COLUMNS}])
    row.loc[0, "media_id"] = media.make_media_id("https://example.com/guard-test")
    row.loc[0, "destination"] = dest
    row.loc[0, "kind"] = "news"
    backup = None
    if media.MEDIA_CSV.exists():
        backup = media.MEDIA_CSV.read_text(encoding="utf-8")
    try:
        row.to_csv(media.MEDIA_CSV, index=False, encoding="utf-8")
        after = aggregate.build_tree(seg)["aspects"]
        for key in before:
            assert before[key]["n_negative"] == after[key]["n_negative"], \
                "media presence changed the complaint count for " + key
            assert before[key]["complaint_rate"] == after[key]["complaint_rate"], \
                "media presence changed the complaint rate for " + key
    finally:
        if backup is not None:
            media.MEDIA_CSV.write_text(backup, encoding="utf-8")
        elif media.MEDIA_CSV.exists():
            media.MEDIA_CSV.unlink()


def test_only_whitelisted_news_domains_are_accepted():
    """An article from an unknown domain is dropped, not shown unsourced."""
    good = media.from_news([{"title": "x", "url": "https://www.adaderana.lk/news/1"}])
    bad = media.from_news([{"title": "x", "url": "https://random-blog.example/post"}])
    assert len(good) == 1 and good[0]["source_name"] == "Ada Derana"
    assert bad == []
