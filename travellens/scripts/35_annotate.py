"""Label the human gold set. Run: python scripts/35_annotate.py

Open problem #1 is that every evaluation label in this project was produced by
the assistant that built the pipeline, which makes the accuracy figures
internally consistent rather than verified. Only a person who did not build
the pipeline can fix that, and this exists to make doing so quick: the whole
200-row focused set should take about twenty minutes.

It writes after every row, so it can be interrupted and resumed, and it never
overwrites a row you have already checked.

  python scripts/35_annotate.py                       # annotator 1, focused set
  python scripts/35_annotate.py --annotator 2         # the second pass
  python scripts/35_annotate.py --file <path>         # any gold set
  python scripts/35_annotate.py --review              # re-read finished rows

At the prompt, name the aspects the PIECE expresses an opinion about:

    r = roads_access   c = cleanliness   f = facilities   s = safety
    (the 600-row set adds  p = price_value  w = crowd  n = scenery)

    s=N          the piece complains about safety
    r=N f=P      complains about access, praises facilities
    c=X          mentions cleanliness as a plain fact, no opinion
    <enter>      none of these aspects is mentioned -- the common case

    ?  guidelines     b  back one row     q  save and quit
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from travellens import config as C  # noqa: E402

def _make_console_utf8():
    """Windows consoles default to cp1252, and reviews contain emoji.

    Without this the tool dies on the first review with a leaf or a flag in
    it -- row 4 of the focused set, four rows in. Reconfiguring with
    errors="replace" means an unrenderable character shows as '?' instead of
    ending the session and losing the reader's place.
    """
    for stream in (sys.stdout, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def say(text=""):
    """print() that cannot kill an annotation session."""
    try:
        print(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(str(text).encode(enc, "replace").decode(enc, "replace"))


KEYS = {
    "r": "roads_access", "c": "cleanliness", "f": "facilities", "s": "safety",
    "p": "price_value", "w": "crowd", "n": "scenery",
}
LABELS = {"N", "P", "X"}
GUIDELINES = C.REPORTS / "ANNOTATION_GUIDELINES.md"


def default_file(annotator: int, focused: bool) -> Path:
    stem = "goldset_focused_annotator" if focused else "goldset_annotator"
    return C.REPORTS / "{}{}.csv".format(stem, annotator)


def parse(entry: str, aspects):
    """Read whatever the annotator typed.

    Accepts, all meaning the same thing:
        r=N     rN     r n     R=n
    and a bare aspect letter with no verdict:
        r       -> ("roads_access", None), so the caller can ask which verdict

    The first version demanded 'r=N' exactly. Somebody labelling 200 rows
    types the shortest thing that could work, and being told "did not
    understand" for pressing 'r' is how a twenty-minute job turns into an
    abandoned one.

    Returns (mapping, pending) where pending lists aspects named without a
    verdict. None means the entry made no sense at all.
    """
    out, pending = {}, []
    tokens = entry.replace(",", " ").replace("=", " ").split()
    i = 0
    while i < len(tokens):
        tok = tokens[i].strip().lower()
        i += 1
        # "rn" -- letter and verdict stuck together
        if len(tok) == 2 and tok[0] in KEYS and tok[1].upper() in LABELS:
            key, verdict = tok[0], tok[1].upper()
        elif tok in KEYS:
            key = tok
            verdict = None
            if i < len(tokens) and tokens[i].strip().upper() in LABELS:
                verdict = tokens[i].strip().upper()
                i += 1
        else:
            return None
        if KEYS[key] not in aspects:
            return None
        if verdict:
            out[KEYS[key]] = verdict
        else:
            pending.append(KEYS[key])
    return out, pending


def show(row, aspects, i, total, done):
    say("\n" + "=" * 70)
    say("  [{}/{}]  {} done   {}".format(
        i + 1, total, done, str(row.get("destination", ""))[:40]))
    say("-" * 70)
    say("  PIECE:  {}".format(str(row.get("segment", "")).strip()))
    full = str(row.get("full_review", "") or "").strip()
    if full and full != str(row.get("segment", "")).strip():
        if len(full) > 600:
            full = full[:600] + " ..."
        say("\n  in the review:\n    {}".format(full.replace("\n", " ")))
    say("-" * 70)
    marks = "  ".join("{}={}".format(k, a) for k, a in KEYS.items()
                      if a in aspects)
    say("  {}".format(marks))


def main():
    ap = argparse.ArgumentParser(description="Label the human gold set.")
    ap.add_argument("--annotator", type=int, default=1, choices=(1, 2))
    ap.add_argument("--file")
    ap.add_argument("--full", action="store_true",
                    help="the 600-row seven-aspect set instead of the focused 200")
    ap.add_argument("--review", action="store_true",
                    help="step through rows already checked")
    args = ap.parse_args()
    _make_console_utf8()

    path = Path(args.file) if args.file else default_file(
        args.annotator, not args.full)
    if not path.exists():
        sys.exit("no such gold set: {}".format(path))

    df = pd.read_csv(path)
    aspects = [c for c in KEYS.values() if c in df.columns]
    if "checked" not in df.columns:
        df["checked"] = ""
    if "notes" not in df.columns:
        df["notes"] = ""
    # Every column we write to must be object dtype up front. pandas reads an
    # all-empty column as float64 and then warns, mid-session, that writing a
    # string into it is deprecated -- which looks like an error to somebody
    # halfway through labelling.
    for a in aspects + ["checked", "notes"]:
        df[a] = df[a].astype("object")

    checked = df["checked"].astype(str).str.strip().str.lower() == "x"
    todo = list(df.index[checked]) if args.review else list(df.index[~checked])

    print("\nLostinSriLanka -- gold set annotation\n" + "=" * 70)
    print("  file    : {}".format(path.name))
    print("  aspects : {}".format(", ".join(aspects)))
    print("  rows    : {} total, {} already checked, {} to do".format(
        len(df), int(checked.sum()), len(todo)))
    print("\n  Label the PIECE, not the review. Most rows are blank -- press")
    print("  enter when no listed aspect carries an opinion. '?' for the")
    print("  guidelines, 'b' to go back, 'q' to save and stop.")
    if not todo:
        print("\n  Nothing to do. All rows are checked.")
        return

    pos = 0
    while 0 <= pos < len(todo):
        idx = todo[pos]
        done = int((df["checked"].astype(str).str.strip().str.lower() == "x").sum())
        show(df.loc[idx], aspects, pos, len(todo), done)
        existing = {a: df.at[idx, a] for a in aspects
                    if pd.notna(df.at[idx, a]) and str(df.at[idx, a]).strip()}
        if existing:
            say("  currently: {}".format(existing))
        try:
            entry = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  stopping -- everything answered so far is saved.")
            break

        if entry.lower() == "q":
            print("\n  saved. Run again to resume.")
            break
        if entry.lower() == "b":
            pos = max(0, pos - 1)
            continue
        if entry == "?":
            if GUIDELINES.exists():
                print("\n" + GUIDELINES.read_text(encoding="utf-8")[:3000])
            else:
                print("  guidelines not found at {}".format(GUIDELINES))
            continue

        parsed = parse(entry, aspects)
        if parsed is None:
            say("  Not a known aspect. Use the letters shown above"
                " (or just press enter if none apply).")
            continue
        picked, pending = parsed

        # A bare letter means "this aspect, but I have not said how yet".
        aborted = False
        for aspect in pending:
            say("    {} -- is the visitor (N)egative, (P)ositive, or is it"
                " (X) just mentioned?".format(aspect))
            try:
                v = input("    N/P/X > ").strip().upper()
            except (EOFError, KeyboardInterrupt):
                aborted = True
                break
            if v in LABELS:
                picked[aspect] = v
            else:
                say("    skipped {} -- press enter at the main prompt to"
                    " leave a row blank".format(aspect))
        if aborted:
            print("\n  stopping -- everything answered so far is saved.")
            break

        for a in aspects:
            df.at[idx, a] = picked.get(a, "")
        df.at[idx, "checked"] = "x"
        # Written every row: a crash or a closed terminal must never cost
        # somebody the labels they already made.
        df.to_csv(path, index=False, encoding="utf-8")
        pos += 1

    final = int((df["checked"].astype(str).str.strip().str.lower() == "x").sum())
    print("\n" + "=" * 70)
    print("  {} of {} rows checked -> {}".format(final, len(df), path))
    if final == len(df):
        print("\n  This set is complete. When BOTH annotators are done:")
        print("    python scripts/05_check_goldset.py")
        print("  which reports inter-annotator agreement -- the number that")
        print("  makes the gold set a measurement rather than one opinion.")
    else:
        print("  Run again to resume.")


if __name__ == "__main__":
    main()
