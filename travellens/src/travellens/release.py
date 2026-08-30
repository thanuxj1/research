"""
LostinSriLanka -- dataset release.

Packages the project's outputs into a citable bundle with a datasheet, so the
work can be handed to someone else and used without this conversation.

What is released, and what is deliberately not
----------------------------------------------
RELEASED -- the derived labels, which are this project's own work:
    aspect assignments, polarity assignments, per-destination scorecards,
    the evaluation sets, and every threshold and routing decision.

WITHHELD -- the full third-party review text. The two source corpora were
scraped from Google Maps and TripAdvisor by other people and redistributing
them wholesale is not this project's right to grant. Segment text is included
only where a quote is needed as evidence, at fair-quotation length, with the
source dataset named. A `text_sha1` column lets anyone holding the original
corpora rejoin the full text themselves.

Why a datasheet
---------------
A CSV without provenance is an orphan. The datasheet states where the data came
from, what was removed and why, which numbers are measured and which are
assumed, and what the release must not be used for. Every known limitation is
in it, including the ones that make the work look weaker.

Run with:  python scripts/24_release.py
"""
import hashlib
import json
import shutil
from datetime import date
from typing import Dict

import pandas as pd

from . import config as C

RELEASE_DIR = C.ROOT / "release"
QUOTE_CHARS = 220        # fair-quotation cap on any included segment text


def _sha1(text: str) -> str:
    return hashlib.sha1(str(text).encode("utf-8", "replace")).hexdigest()[:16]


def build_enriched(verbose: bool = True) -> pd.DataFrame:
    """One row per (segment, aspect) with the label this project assigned."""
    seg = pd.read_csv(C.DATA_PROCESSED / "segments_tagged_union.csv")
    sc = pd.read_csv(C.DATA_PROCESSED / "segments_scored.csv")
    pol = [c for c in sc.columns if c.startswith("pol_")]
    seg = seg.merge(sc[["segment_id"] + pol], on="segment_id", how="left")
    # Take whichever provenance columns the corpus actually has. `source_url`
    # and `review_date` were added after the two legacy datasets were ingested,
    # so an older corpus file will not carry them; missing is not an error.
    rev_all = pd.read_csv(C.CLEAN_REVIEWS_CSV)
    wanted = ["review_id", "source", "rating", "review_date", "source_url"]
    have = [c for c in wanted if c in rev_all.columns]
    missing = [c for c in wanted if c not in rev_all.columns]
    if missing and verbose:
        print("  corpus lacks {} -- released as empty".format(", ".join(missing)))
    seg = seg.merge(rev_all[have], on="review_id", how="left")
    for c in missing:
        seg[c] = pd.NA

    try:
        from .aspects_model import ASPECT_EXTRACTOR
    except ImportError:
        ASPECT_EXTRACTOR = {}

    rows = []
    for key in C.ASPECTS:
        pick = ASPECT_EXTRACTOR.get(key, "rules")
        col = {"trained": "tAsp_", "safety_model": "sAsp_",
               "union": "uAsp_"}.get(pick, "asp_") + key
        if col not in seg.columns:
            col = "asp_" + key
        sub = seg[seg[col].fillna(False)]
        for r in sub.itertuples(index=False):
            rows.append({
                "segment_id": r.segment_id,
                "review_id": r.review_id,
                "destination": r.destination,
                "district": r.district,
                "aspect": key,
                "polarity": getattr(r, "pol_final", None),
                "extractor": pick,
                "recency_band": getattr(r, "recency", None),
                "source_dataset": getattr(r, "source", None),
                "star_rating": getattr(r, "rating", None),
                "review_date": getattr(r, "review_date", None),
                "source_url": getattr(r, "source_url", None),
                "text_sha1": _sha1(r.segment),
                "text_excerpt": str(r.segment)[:QUOTE_CHARS],
            })
    df = pd.DataFrame(rows)
    if verbose:
        print("  enriched rows        : {}".format(len(df)))
        print("  distinct segments    : {}".format(df["segment_id"].nunique()))
        print("  destinations         : {}".format(df["destination"].nunique()))
    return df


def datasheet(enriched: pd.DataFrame) -> str:
    cleaning = json.load(open(C.CLEANING_REPORT_JSON, encoding="utf-8"))
    corpus = pd.read_csv(C.CLEAN_REVIEWS_CSV)
    try:
        lex = json.load(open(C.REPORTS / "lexicon_final_scores.json", encoding="utf-8"))
    except Exception:
        lex = {}

    by_source = corpus["source"].value_counts().to_dict()
    pol = enriched["polarity"].value_counts().to_dict()

    lines = []
    A = lines.append
    A("# LostinSriLanka — Dataset Datasheet")
    A("")
    A("Generated {}.".format(date.today().isoformat()))
    A("")
    A("## 1. What this is")
    A("")
    A("Aspect-level opinion labels for tourist reviews of Sri Lankan destinations.")
    A("Each row records that one sentence expressed a complaint, a compliment, or a")
    A("plain fact about one topic at one place.")
    A("")
    A("| | |")
    A("|---|---|")
    A("| Labelled rows | {} |".format(len(enriched)))
    A("| Distinct sentences | {} |".format(enriched["segment_id"].nunique()))
    A("| Destinations | {} |".format(enriched["destination"].nunique()))
    A("| Districts | {} |".format(enriched["district"].nunique()))
    A("| Aspects | {} |".format(enriched["aspect"].nunique()))
    A("| Complaint / praise / factual | {} / {} / {} |".format(
        pol.get("N", 0), pol.get("P", 0), pol.get("X", 0)))
    A("")
    A("## 2. Where the reviews came from")
    A("")
    for src, n in by_source.items():
        A("- **{}** — {:,} reviews".format(src, n))
    A("")
    A("Full provenance, including one source that could not be traced, is in")
    A("`SOURCES.md`. **Neither source corpus preserved review URLs**, so individual")
    A("quoted sentences cannot be linked back to the original review. Destination-level")
    A("search links are provided instead. Reviews collected by this project after")
    A("release carry a `source_url`.")
    A("")
    A("## 3. What was removed, and why")
    A("")
    A("| Stage | Rows left | Removed |")
    A("|---|---|---|")
    for st in cleaning["stages"]:
        A("| {} | {:,} | {} |".format(
            st["stage"].split("_", 1)[-1].replace("_", " "),
            st["rows_after"], st["rows_removed"] or ""))
    A("")
    A("{}% of reviews are truncated mid-sentence by the source platform's".format(
        cleaning["pct_truncated"]))
    A("\"read more\" behaviour. They were **kept and flagged**, not dropped; testing")
    A("found their complaint rates differ from untruncated reviews by under one")
    A("percentage point, in both directions, so truncation does not bias the results.")
    A("")
    A("## 4. How the labels were produced")
    A("")
    A("Reviews are split into single-opinion sentences, assigned to topics, then")
    A("classified as complaint / praise / factual. Topic extraction is chosen **per")
    A("aspect by measurement**, not by preference:")
    A("")
    A("| Aspect | Extractor | F1 | Test positives |")
    A("|---|---|---|---|")
    try:
        from .aspects_model import ASPECT_EXTRACTOR
    except ImportError:
        ASPECT_EXTRACTOR = {}
    scores = {"roads_access": ("trained", "0.914", "33"),
              "facilities": ("trained", "0.773", "21"),
              "safety": ("safety_model", "0.755", "22"),
              "cleanliness": ("rules", "0.901", "36"),
              "price_value": ("rules", "0.976", "21"),
              "crowd": ("rules", "0.903", "16"),
              "scenery": ("rules", "0.906", "25")}
    for k, (ex, f1, n) in scores.items():
        A("| {} | {} | {} | {} |".format(k, ASPECT_EXTRACTOR.get(k, ex), f1, n))
    A("")
    A("Polarity uses `cardiffnlp/twitter-roberta-base-sentiment-latest` with two")
    A("documented correction rules. A model trained on star-derived weak labels")
    A("scored higher in aggregate (macro-F1 0.797 vs 0.691) but inverted 55% of")
    A("safety complaints, and is **excluded from the pipeline** for that reason.")
    A("")
    A("## 5. Limitations — read before using")
    A("")
    A("1. **No independent human validation.** Every evaluation set in this release")
    A("   was labelled by the system's own author. The scores are internally")
    A("   consistent comparisons, **not** verified accuracy. An independently")
    A("   annotated gold set is the outstanding work.")
    A("2. **Complaint rate is not risk.** It is the share of *expressed opinions*")
    A("   that are negative. People rarely praise a road that simply worked, so")
    A("   every aspect is biased toward complaint once mentioned. Compare rates")
    A("   *between* destinations; never read one as a probability of a bad visit.")
    A("3. **Platform, not nationality.** Of 16,156 TripAdvisor reviewers exactly one")
    A("   lists Sri Lanka as home; the Google corpus has no reviewer-origin field at")
    A("   all. Differences between the corpora are **platform** differences. The")
    A("   domestic-versus-international reading is an interpretation, not a finding.")
    A("4. **Coverage.** 19 of 22 districts. Monaragala, Puttalam and the Vanni have")
    A("   no reviews in either corpus.")
    A("5. **Three hand-written correction rules** remain unvalidated: a domain patch,")
    A("   a polite-complaint rule and a safety recall rule. Each was written in")
    A("   response to an observed failure; none has been measured against")
    A("   independent labels.")
    A("6. **Time.** Reviews span 2011–2024. Testing found a destination's historical")
    A("   complaint rate predicts its current one at r≈0.6, *flat* from one to seven")
    A("   years, so no recency weighting is applied. A resolved problem still")
    A("   appears in the data until newer reviews outnumber older ones.")
    A("")
    A("## 6. What this must not be used for")
    A("")
    A("- **Safety decisions.** Safety labels are the least reliable in the set")
    A("  (F1 0.755, the lowest of seven) and the corpus records opinions, not")
    A("  incidents. Do not use it to decide whether a place is safe to visit.")
    A("- **Ranking or penalising individual businesses or operators.**")
    A("- **Any claim about Sri Lanka as a whole.** Three districts are absent.")
    A("- **Redistribution of the underlying review text.** Excerpts here are")
    A("  quotation-length evidence; the full corpora belong to their original")
    A("  collectors.")
    A("")
    A("## 7. Files")
    A("")
    A("| File | Contents |")
    A("|---|---|")
    A("| `enriched_labels.csv` | One row per (sentence, aspect) with its label |")
    A("| `scorecards.csv` | One row per (destination, aspect) with counts and rates |")
    A("| `evaluation_sets/` | The author-labelled test sets, with their labels |")
    A("| `SOURCES.md` | Provenance for every input, including unresolved gaps |")
    A("| `DATASHEET.md` | This file |")
    A("")
    A("## 8. Citing the models used")
    A("")
    A("Two pretrained models are applied and are **not** contributions of this work:")
    A("`distilbert-base-uncased-finetuned-sst-2-english` and")
    A("`cardiffnlp/twitter-roberta-base-sentiment-latest`. District boundaries are")
    A("CC-BY from `thejeshgn/srilanka`, derived from GADM 2.7 — attribution required.")
    return "\n".join(lines)


def main():
    print("\nLostinSriLanka -- dataset release\n" + "=" * 60)
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    (RELEASE_DIR / "evaluation_sets").mkdir(exist_ok=True)

    enriched = build_enriched()
    enriched.to_csv(RELEASE_DIR / "enriched_labels.csv", index=False, encoding="utf-8")

    shutil.copy2(C.DATA_PROCESSED / "scorecards.csv", RELEASE_DIR / "scorecards.csv")
    shutil.copy2(C.DATA_RAW / "SOURCES.md", RELEASE_DIR / "SOURCES.md")

    for name in ("eval_sample.csv", "safety_eval_sample.csv",
                 "clean_eval_sample.csv", "price_eval_sample.csv",
                 "cs_eval_sample.csv"):
        src = C.REPORTS / name
        if src.exists():
            shutil.copy2(src, RELEASE_DIR / "evaluation_sets" / name)
    for name in ("eval_labels.py", "safety_eval_labels.py", "clean_eval_labels.py",
                 "price_eval_labels.py", "cs_eval_labels.py"):
        src = C.REPORTS / name
        if src.exists():
            shutil.copy2(src, RELEASE_DIR / "evaluation_sets" / name)

    sheet = datasheet(enriched)
    (RELEASE_DIR / "DATASHEET.md").write_text(sheet, encoding="utf-8")

    total = sum(f.stat().st_size for f in RELEASE_DIR.rglob("*") if f.is_file())
    print("\n  release/ contains {} files, {:.1f} MB".format(
        sum(1 for f in RELEASE_DIR.rglob("*") if f.is_file()), total / 1e6))
    print("  wrote {}".format(RELEASE_DIR / "DATASHEET.md"))


if __name__ == "__main__":
    main()
