"""Export a spreadsheet to label by hand, and read it back in.

  python scripts/36_annotation_sheet.py --export
  python scripts/36_annotation_sheet.py --export --annotator 2
  python scripts/36_annotation_sheet.py --import-from <the filled file>

Same job as scripts/35_annotate.py, for people who would rather work in Excel
or Sheets than in a terminal. The result is identical: a human verdict on each
piece, which is the one thing in this project that cannot be automated.

Two details that matter more than they look:

  * The sheet does NOT carry sample_reason. That column records why a row was
    picked -- "representative:safety", "disagreement:cleanliness" -- which is
    the pipeline's own guess. An annotator who can see the expected answer is
    not an independent annotator, and independence is the entire point.

  * It is written UTF-8 with a BOM, because Excel assumes the local codepage
    otherwise and turns every Sinhala name and emoji into mojibake. The
    imported labels would be fine either way; the reviews would be unreadable
    while labelling, which is worse.

The import validates every cell, refuses to write anything it does not
understand, and never touches a row you left blank.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from travellens import config as C  # noqa: E402

ASPECTS = ["roads_access", "cleanliness", "facilities", "safety"]
VALID = {"N", "P", "X"}
# The pipeline's guess about the row. Never exported -- see module docstring.
BIASING = ["sample_reason", "n_distinct_labels"]


def goldset_path(annotator, full=False):
    stem = "goldset_annotator" if full else "goldset_focused_annotator"
    return C.REPORTS / "{}{}.csv".format(stem, annotator)


def export(annotator, full=False):
    src = goldset_path(annotator, full)
    df = pd.read_csv(src)
    aspects = [a for a in df.columns if a in ASPECTS] or ASPECTS

    out = pd.DataFrame()
    out["row"] = df["row"]
    out["segment_id"] = df["segment_id"]
    out["destination"] = df["destination"]
    out["THIS_IS_WHAT_YOU_JUDGE"] = df["segment"]
    out["for_context_only_the_whole_review"] = df.get("full_review", "")
    for a in aspects:
        out[a] = df[a] if a in df.columns else ""
    out["notes"] = df.get("notes", "")

    for col in BIASING:
        assert col not in out.columns, "the sheet must not carry " + col

    dest = C.REPORTS / "TO_LABEL_annotator{}.csv".format(annotator)
    # utf-8-sig: Excel needs the BOM to read this as UTF-8.
    out.to_csv(dest, index=False, encoding="utf-8-sig")
    print("\n  wrote {}".format(dest))
    print("  {} rows, {} aspect columns to fill in".format(len(out), len(aspects)))
    print("\n  Fill in N / P / X, or leave blank. Most rows stay blank.")
    print("    N = the visitor is complaining about it")
    print("    P = the visitor is praising it")
    print("    X = mentioned, but no opinion either way")
    print("\n  Judge the THIS_IS_WHAT_YOU_JUDGE column only. The whole review")
    print("  is there so you can tell what that piece means, not to be judged.")
    print("\n  When done:")
    print("    python scripts/36_annotation_sheet.py --import-from <file>")
    return dest


def read_back(filled, annotator, full=False):
    src = Path(filled)
    if not src.exists():
        sys.exit("no such file: {}".format(src))
    # utf-8-sig strips the BOM if Excel kept it, and is harmless if not.
    try:
        sheet = pd.read_csv(src, encoding="utf-8-sig")
    except UnicodeDecodeError:
        # Excel on a non-UTF-8 machine may have saved it in the local codepage.
        sheet = pd.read_csv(src, encoding="cp1252")
        print("  note: read as cp1252 -- Excel did not keep UTF-8")

    if "segment_id" not in sheet.columns:
        sys.exit("that file has no segment_id column -- is it the right sheet?")

    gold = pd.read_csv(goldset_path(annotator, full))
    aspects = [a for a in ASPECTS if a in gold.columns and a in sheet.columns]
    if not aspects:
        sys.exit("no aspect columns found in that sheet")
    for a in aspects + ["checked", "notes"]:
        if a not in gold.columns:
            gold[a] = ""
        gold[a] = gold[a].astype("object")

    by_id = {str(r["segment_id"]): r for r in sheet.to_dict("records")}
    problems, filled_rows, blank_rows = [], 0, 0

    for i, r in gold.iterrows():
        sid = str(r["segment_id"])
        if sid not in by_id:
            continue
        entry = by_id[sid]
        values, bad = {}, False
        for a in aspects:
            raw = entry.get(a, "")
            v = "" if pd.isna(raw) else str(raw).strip().upper()
            if v in ("", "-", "NAN"):
                values[a] = ""
            elif v in VALID:
                values[a] = v
            else:
                problems.append("row {}: {} = '{}' (expected N, P, X or blank)"
                                .format(entry.get("row", sid), a, raw))
                bad = True
        if bad:
            continue
        # A row is "done" only if the person actually looked at it. An
        # untouched sheet is all blanks, and importing those as 200 confident
        # "nothing here" verdicts would fabricate a gold set out of an empty
        # spreadsheet.
        touched = any(values.values()) or str(
            entry.get("checked", "")).strip().lower() in ("x", "yes", "1")
        if not touched:
            blank_rows += 1
            continue
        for a in aspects:
            gold.at[i, a] = values[a]
        note = entry.get("notes", "")
        gold.at[i, "notes"] = "" if pd.isna(note) else str(note)
        gold.at[i, "checked"] = "x"
        filled_rows += 1

    if problems:
        print("\n  NOT IMPORTED -- {} cell(s) I could not read:".format(len(problems)))
        for p in problems[:20]:
            print("    {}".format(p))
        if len(problems) > 20:
            print("    ... and {} more".format(len(problems) - 20))
        print("\n  Fix those cells and run this again. Nothing was written.")
        return None

    dest = goldset_path(annotator, full)
    gold.to_csv(dest, index=False, encoding="utf-8")
    print("\n  imported {} labelled rows -> {}".format(filled_rows, dest.name))
    if blank_rows:
        print("  {} rows left entirely blank were SKIPPED, not recorded as".format(
            blank_rows))
        print("  'nothing here'. Mark 'x' in a checked column if a blank row")
        print("  really is your verdict.")
    print("\n  next: python scripts/05_check_goldset.py")
    return dest


def main():
    ap = argparse.ArgumentParser(description="Spreadsheet in, spreadsheet out.")
    ap.add_argument("--export", action="store_true")
    ap.add_argument("--import-from", dest="import_from")
    ap.add_argument("--annotator", type=int, default=1, choices=(1, 2))
    ap.add_argument("--full", action="store_true")
    args = ap.parse_args()

    print("\nLostinSriLanka -- annotation sheet\n" + "=" * 60)
    if args.export:
        export(args.annotator, args.full)
    elif args.import_from:
        read_back(args.import_from, args.annotator, args.full)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
