"""
Backfill per-aspect polarity for submissions stored before it existed.

Why
---
user_segments used to hold one polarity per segment. The API broadcast that
single label across every aspect the segment mentioned, so a sentence tagged
safety + scenery contributed the safety verdict to the scenery count. The
column that fixes this -- aspect_polarity -- is added by the schema migration
in submissions_db.py, but a migration can only add it empty: rows written
before the change have no per-aspect verdicts to move into it, and there is
no way to derive them from the stored label.

So they are recomputed here, from the stored segment text, through exactly
the pipeline the API now runs: final_polarity() for the segment-level
verdict, then polarity.aspect_polarity() per aspect. Same functions,
same order, same result as a fresh submission.

Until this runs, /stats reports those rows under `segments_awaiting_rescore`
and leaves them out of the complaint counts rather than guessing at them.

Usage
-----
    python scripts/42_rescore_submissions.py            # rescore what's missing
    python scripts/42_rescore_submissions.py --all      # redo every row
    python scripts/42_rescore_submissions.py --dry-run  # report, change nothing

Reads SUBMISSIONS_DATABASE_URL the same way the API does, so it rescores
whichever backend the API is actually writing to. Loading the transformer
takes a few seconds; scoring is one model call per segment.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from travellens.aspects import tag_segment                    # noqa: E402
from travellens.polarity import (                             # noqa: E402
    aspect_polarity,
    final_polarity,
    lexicon_polarity,
)
from travellens.submissions_db import active_backend, connection  # noqa: E402


def _load_model():
    """Method E's transformer, or None to fall back to the lexicon -- the
    same choice, made the same way, as api._get_polarity_method()."""
    try:
        from travellens.polarity import (
            TransformerPolarity, ROBERTA_MODEL, ROBERTA_LABELS)
        model = TransformerPolarity(
            model_name=ROBERTA_MODEL, label_map=ROBERTA_LABELS)
        model._load()
        print("  polarity method: E (transformer + correction rules)")
        return model
    except Exception as exc:
        print("  transformer unavailable ({}), using lexicon".format(exc))
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true",
                    help="rescore every segment, not only unscored ones")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change, write nothing")
    args = ap.parse_args()

    print("\nLostinSriLanka -- rescore user submissions\n" + "=" * 60)
    print("  backend: {}".format(active_backend()))

    where = "" if args.all else "WHERE aspect_polarity IS NULL"
    with connection() as con:
        rows = con.execute(
            "SELECT id, segment_text, aspects, polarity "
            "FROM user_segments {} ORDER BY id".format(where)
        ).fetchall()
        rows = [dict(r) for r in rows]

    if not rows:
        print("\n  nothing to do -- every segment already has per-aspect "
              "verdicts.\n")
        return

    print("  segments to score: {:,}".format(len(rows)))
    model = _load_model()

    updates = []
    changed = 0
    for r in rows:
        text = r["segment_text"] or ""
        # Re-tag rather than trusting the stored aspects column: if the
        # lexicon has changed since the row was written, the stored aspects
        # are stale too, and a per-aspect verdict for an aspect the segment
        # no longer carries would be worse than no verdict at all.
        keys = tag_segment(text)
        lex_label, lex_score = lexicon_polarity(text)

        if model is not None and keys:
            model_label = model.predict([text], verbose=False)[0]["label"]
            label, _ = final_polarity(text, model_label, lex_label, lex_score)
        else:
            label = lex_label

        per_aspect = {}
        for key in keys:
            per_aspect[key], _, _ = aspect_polarity(text, key, label, lex_label)

        # Did the broadcast label the old code used actually differ from the
        # per-aspect verdicts? That count is the size of the bug in this data.
        if any(v != r["polarity"] for v in per_aspect.values()):
            changed += 1

        updates.append((
            json.dumps(per_aspect, sort_keys=True, separators=(",", ":")),
            json.dumps(keys),
            label,
            r["id"],
        ))

    print("  segments whose per-aspect verdict differs from the stored "
          "segment label: {:,}".format(changed))

    if args.dry_run:
        print("\n  --dry-run: nothing written.\n")
        return

    with connection() as con:
        for payload, aspects_json, label, row_id in updates:
            con.execute(
                "UPDATE user_segments "
                "SET aspect_polarity = ?, aspects = ?, polarity = ? "
                "WHERE id = ?",
                (payload, aspects_json, label, row_id),
            )
        con.commit()

    print("\n  wrote {:,} rows.\n".format(len(updates)))


if __name__ == "__main__":
    main()
