"""
TravelLens LK -- Stage 1: corpus cleaning.

Design rule: this module NEVER silently drops a row. Every filter records how
many rows it removed and why, and the counts are written to
reports/cleaning_report.json so the thesis can quote them directly.

Run with:  python scripts/01_clean.py
"""
import hashlib
import json
import re
from typing import Optional, Tuple

import pandas as pd

from . import config as C


# --------------------------------------------------------------------------
# Timespan parsing
#
# The corpus stores only a RELATIVE age ("4 years ago"), never an absolute
# date. We convert to approximate months so reviews can be bucketed by
# recency, but we deliberately do NOT reconstruct calendar dates -- that would
# imply a precision the data does not have.
# --------------------------------------------------------------------------
_TIMESPAN_RE = re.compile(r"^(a|an|\d+)\s+(day|week|month|year)s?\s+ago$", re.I)
_UNIT_MONTHS = {"day": 1.0 / 30.0, "week": 0.25, "month": 1.0, "year": 12.0}


def parse_timespan(value: str) -> Optional[float]:
    """'4 years ago' -> 48.0 months. Returns None if unparseable."""
    if not isinstance(value, str):
        return None
    m = _TIMESPAN_RE.match(value.strip())
    if not m:
        return None
    qty_raw, unit = m.group(1), m.group(2).lower()
    qty = 1.0 if qty_raw.lower() in ("a", "an") else float(qty_raw)
    return qty * _UNIT_MONTHS[unit]


def recency_bucket(months: Optional[float]) -> str:
    """Coarse buckets. Coarse on purpose -- the source precision is low."""
    if months is None:
        return "unknown"
    if months <= 12:
        return "0-1y"
    if months <= 36:
        return "1-3y"
    if months <= 60:
        return "3-5y"
    return "5y+"


# --------------------------------------------------------------------------
# Text normalisation
# --------------------------------------------------------------------------
_WS_RE = re.compile(r"\s+")
# Repeated '?' blocks are how the scraper rendered Sinhala/Tamil script it could
# not encode. They are noise, not punctuation.
_LOST_SCRIPT_RE = re.compile(r"\?{3,}")
_REPLACEMENT_RE = re.compile("�+")


def normalise_text(text: str) -> str:
    """Whitespace, lost-script markers and mojibake -- not lowercasing.

    We keep original casing and punctuation: transformer models use both, and
    stripping them is exactly the mistake the Kaggle 'final' file makes.
    """
    if not isinstance(text, str):
        return ""
    text = _LOST_SCRIPT_RE.sub(" ", text)
    text = _REPLACEMENT_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text)
    return text.strip()


def word_count(text: str) -> int:
    return len(text.split())


def make_review_id(destination: str, text: str, timespan: str = "") -> str:
    """Stable content hash used to recognise a review we already hold.

    Built from destination + text ONLY. `timespan` is accepted for call-site
    compatibility but deliberately ignored, because Google stores review age
    relatively: a review reading "2 years ago" today reads "3 years ago" next
    year. Including it would give the same review a different id on every
    refresh, so each re-scrape would re-insert reviews already in the corpus
    and inflate every complaint count. Identity must be built only from fields
    that do not change.

    Collision risk is the same one Stage 1 already accepts when it de-duplicates
    on (destination, text): two visitors writing byte-identical reviews of the
    same place are treated as one. With a 4-word minimum this is rare, and
    counting it once is the safer error.
    """
    raw = "|".join([str(destination).strip().lower(), str(text).strip()])
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:16]


# --------------------------------------------------------------------------
# Main cleaning routine
# --------------------------------------------------------------------------
def clean_corpus(csv_path=None, verbose: bool = True) -> Tuple[pd.DataFrame, dict]:
    """Load the raw scrape and return (clean_dataframe, audit_report)."""
    csv_path = csv_path or C.RAW_REVIEWS_CSV
    report = {"source_file": str(csv_path), "stages": []}

    def log(stage: str, df: pd.DataFrame, removed: int = 0, note: str = ""):
        entry = {"stage": stage, "rows_after": len(df), "rows_removed": removed, "note": note}
        report["stages"].append(entry)
        if verbose:
            msg = "  {:<28} rows={:>6}".format(stage, len(df))
            if removed:
                msg += "  (-{})".format(removed)
            if note:
                msg += "  # " + note
            print(msg)

    # The scrape is mostly UTF-8 with a handful of stray CP-1252 bytes. We
    # decode permissively and count the damage rather than crashing.
    df = pd.read_csv(csv_path, encoding="utf-8", encoding_errors="replace")
    df.columns = [c.strip() for c in df.columns]
    log("0_loaded", df)
    report["columns"] = list(df.columns)

    # -- Structural completeness -------------------------------------------
    before = len(df)
    df = df.dropna(subset=["Review", "Destination", "District"])
    log("1_drop_missing_fields", df, before - len(df), "null Review/Destination/District")

    # -- Flag encoding damage BEFORE we strip it ---------------------------
    mojibake = df["Review"].astype(str).str.contains("�|\\?{3,}", regex=True)
    report["rows_with_encoding_damage"] = int(mojibake.sum())
    if verbose:
        print("  {:<28} {} rows carried unencodable script (Sinhala/Tamil)".format(
            "note_encoding", int(mojibake.sum())))

    # -- Truncation flag (kept, not dropped) -------------------------------
    df = df.copy()
    df["is_truncated"] = df["Review"].astype(str).str.contains(
        C.TRUNCATION_MARKER, regex=False)
    report["rows_truncated"] = int(df["is_truncated"].sum())
    report["pct_truncated"] = round(100 * df["is_truncated"].mean(), 2)
    if verbose:
        print("  {:<28} {} rows ({}%) cut off by 'read more' -- KEPT and flagged".format(
            "note_truncation", report["rows_truncated"], report["pct_truncated"]))

    # -- Text normalisation ------------------------------------------------
    df["text"] = df["Review"].astype(str).map(normalise_text)
    df["n_words"] = df["text"].map(word_count)

    before = len(df)
    df = df[df["text"].str.len() > 0]
    log("2_drop_empty_after_norm", df, before - len(df), "review was only noise characters")

    # -- Minimum-content filter --------------------------------------------
    before = len(df)
    dropped_short = df[df["n_words"] < C.MIN_WORDS]
    report["top_dropped_short"] = (
        dropped_short["text"].str.lower().value_counts().head(10).to_dict())
    df = df[df["n_words"] >= C.MIN_WORDS]
    log("3_drop_too_short", df, before - len(df),
        "fewer than {} words -- no recoverable opinion".format(C.MIN_WORDS))

    # -- Duplicates --------------------------------------------------------
    before = len(df)
    df = df.drop_duplicates(subset=["Destination", "text"])
    log("4_drop_duplicates", df, before - len(df), "same text at same destination")

    # -- Derived fields ----------------------------------------------------
    df["district_raw"] = df["District"].astype(str).str.strip()
    df["district"] = df["district_raw"].map(C.DISTRICT_CANON).fillna(df["district_raw"])
    df["destination"] = df["Destination"].astype(str).str.strip()
    df["months_ago"] = df["Timespan"].map(parse_timespan)
    df["recency"] = df["months_ago"].map(recency_bucket)
    report["unparsed_timespan"] = int(df["months_ago"].isna().sum())

    df["review_id"] = [
        make_review_id(d, t, ts)
        for d, t, ts in zip(df["destination"], df["text"], df["Timespan"])
    ]

    # -- Provenance --------------------------------------------------------
    # Every review records where it came from and when it entered the corpus.
    # Reviews added later by the refresh pipeline carry their own source tag,
    # so any change in a published number can be traced to the batch that
    # caused it. `rating` is empty for this corpus (the Kaggle scrape has no
    # star ratings) but present in the schema, because newly collected Google
    # reviews DO carry stars -- see ingest.py.
    df["source"] = "kaggle_2024_03"
    df["collected_at"] = "2024-03-25"
    df["rating"] = pd.NA
    # Empty for this corpus: the Kaggle export preserved no review URL, and a
    # Google Maps review permalink cannot be reconstructed without a place id
    # and a review id, neither of which the export contains. Populated at
    # collection time for anything scraped from here on -- a URL captured
    # during collection is free, and one reconstructed afterwards is impossible.
    df["source_url"] = pd.NA

    df = df[[
        "review_id", "destination", "district", "district_raw",
        "text", "n_words", "is_truncated", "months_ago", "recency",
        "source", "collected_at", "rating", "source_url",
    ]].reset_index(drop=True)

    # -- Final corpus summary ----------------------------------------------
    report["final"] = {
        "reviews": len(df),
        "destinations": int(df["destination"].nunique()),
        "districts": int(df["district"].nunique()),
        "median_words": float(df["n_words"].median()),
        "mean_words": round(float(df["n_words"].mean()), 2),
        "retention_pct": round(100 * len(df) / report["stages"][0]["rows_after"], 2),
    }
    return df, report


def main():
    print("\nTravelLens LK -- Stage 1: cleaning\n" + "=" * 60)
    df, report = clean_corpus()

    C.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    df.to_csv(C.CLEAN_REVIEWS_CSV, index=False, encoding="utf-8")
    with open(C.CLEANING_REPORT_JSON, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    f = report["final"]
    print("\n" + "=" * 60)
    print("KEPT {} of {} reviews ({}%)".format(
        f["reviews"], report["stages"][0]["rows_after"], f["retention_pct"]))
    print("  {} destinations across {} districts".format(f["destinations"], f["districts"]))
    print("  median length {} words".format(int(f["median_words"])))
    print("\nwrote {}".format(C.CLEAN_REVIEWS_CSV))
    print("wrote {}".format(C.CLEANING_REPORT_JSON))


if __name__ == "__main__":
    main()
