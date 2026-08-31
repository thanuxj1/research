"""
LostinSriLanka -- real-time review analysis API.

Design decisions (documented here so they travel with the code):

  POLARITY METHOD: transformer + correction rules (Method E) → lexicon fallback (Method A)
  ──────────────────────────────────────────────────────────────────────────
  This used to load Method F, models/travellens-polarity/, the checkpoint
  fine-tuned on STAR-derived weak labels. That was this API's first accuracy
  bug: reports/method_f_safety_audit.json exists specifically to argue
  against deploying it, because most safety WARNINGS sit inside 5-star
  reviews, so F learned that hedged hazard language reads as praise -- it
  flipped 55.3% of safety complaints to positive. finetune_report.json's own
  headline number for F (macro-F1 0.797) carries this caveat in the same
  file: "Test labels are star-derived, from the same weak source as the
  training labels. This score measures AGREEMENT WITH STAR RATINGS, not
  accuracy."

  Six post-hoc override rules had accumulated here to patch that failure mode
  phrase by phrase. They were kept after the cause was removed, and that was
  this API's SECOND accuracy bug: they existed nowhere in the batch pipeline,
  so the endpoint and the dashboard gave different verdicts for the same
  sentence. Replaying all 85,539 segment-aspect pairs in segments_scored.csv
  through both chains found 360 disagreements -- 97 of them scenery segments
  the dashboard counts as complaints and this endpoint reported as PRAISE
  ("A beautiful natural place killed by humans." → positive). All six are
  gone.

  What runs now is exactly what aggregate.py runs, because both call the same
  function: polarity.final_polarity() for the segment-level verdict, then
  polarity.aspect_polarity() for the per-aspect chain (safety recall, then
  site rule). One definition, two callers, zero drift -- enforced by
  tests/test_api_pipeline_parity.py, which replays a corpus sample through
  both and fails on any disagreement.

  Note the shape that follows from this: polarity is per (segment, ASPECT),
  not per segment. "The view is stunning but the rocks are dangerous" is a
  safety complaint and a scenery compliment, and the response says so.

  Polarity accuracy against real human labels is measured in
  reports/polarity_accuracy_deployed.json -- the first time that number has
  existed for the deployed system; every earlier figure scored aspect
  PRESENCE only, never whether a correctly-identified aspect's polarity call
  actually matched a human's.

  CORPUS SEPARATION: user_submissions.db, not travellens.db
  ──────────────────────────────────────────────────────────
  The research corpus has documented provenance and F1 scores measured against
  a human gold set. Injecting user submissions into travellens.db would silently
  mix unvalidated input into those numbers. The submissions live in their own
  file. Running `python scripts/29_load_db.py` can never touch them.

Run:  python scripts/41_serve_api.py
      PORT=9000 python scripts/41_serve_api.py
"""
import json
import os
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from . import config as C
from .aspects import matched_terms, tag_segment
from .polarity import (
    aspect_polarity,
    lexicon_polarity,
    final_polarity,
)
# TrainedPolarity and trained_model_available() were Method F's (the
# star-label fine-tune) loader and its availability check. Neither is called
# anywhere below any more -- Method E loads TransformerPolarity directly,
# lazily, inside _get_polarity_method(). Not re-imported here on purpose:
# an unused import of the thing this file's docstring explains NOT to use
# is exactly the kind of leftover that regrows into a second accidental
# regression the way the model-mismatch bug did.
from .segment import split_into_segments, MIN_SEGMENT_WORDS

# Six regex-driven override rules used to sit here: a roads difficulty
# override, a crowd complaint override, a strong-lexicon override, a
# cleanliness rescue, a scenery rescue, and a post-model safety override with
# its own negated-hazard guard. Every one of them was written to compensate
# for Method F's star-label inversions, and every one of them outlived the
# model it was patching.
#
# They are not re-added here in weakened form, because the problem was never
# any single rule's precision -- it was that they existed in this file and
# not in the pipeline, so the endpoint and the dashboard disagreed on 360 of
# 85,539 verdicts. Any correction rule this API needs belongs in polarity.py,
# where aggregate.py picks it up too, with its effect on the published
# figures measured through ablation.py first. That is the standard the three
# surviving rules (final_polarity, safety_recall_rule,
# site_rule_is_not_a_complaint) were each held to.


# --------------------------------------------------------------------------
# Request limits
# --------------------------------------------------------------------------
# /analyse is an unauthenticated POST that runs a transformer once per
# segment and writes a row. Every one of these numbers is a bound that was
# missing: a 144 KB body analysed for 353 seconds and returned 4,000
# segments, holding a worker thread for the whole time.
#
# 5,000 characters is generous for a review -- the longest in the 46,854-review
# corpus is well under it -- and 120 segments is more opinion units than any
# real review carries.
MAX_TEXT_CHARS = 5_000
MAX_SEGMENTS_PER_REVIEW = 120

# Simple fixed-window per-IP limit for the write endpoint. In-process and
# per-worker, so it is a brake rather than a guarantee -- it stops one client
# filling the corpus, and anything stronger belongs at the reverse proxy.
RATE_LIMIT_REQUESTS = int(os.environ.get("ANALYSE_RATE_LIMIT") or 30)
RATE_LIMIT_WINDOW_SECONDS = 60
_rate_hits: Dict[str, deque] = {}
_rate_lock = threading.Lock()


def _rate_limited(client_ip: str) -> bool:
    """True when this IP has spent its budget for the current window."""
    now = time.monotonic()
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS
    with _rate_lock:
        hits = _rate_hits.setdefault(client_ip, deque())
        while hits and hits[0] < cutoff:
            hits.popleft()
        if len(hits) >= RATE_LIMIT_REQUESTS:
            return True
        hits.append(now)
        # Drop idle clients so the dict cannot grow without bound.
        if len(_rate_hits) > 2048:
            for ip in [k for k, v in _rate_hits.items() if not v or v[-1] < cutoff]:
                del _rate_hits[ip]
        return False


# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
# Storage lives in submissions_db.py: local SQLite by default, Postgres
# (Neon) if SUBMISSIONS_DATABASE_URL is set. See that module for why -- the
# short version is that an ephemeral filesystem on a hosted deploy would
# silently lose every submission on the next restart.
#
# Call sites use `with connection() as con:` rather than get_connection()
# plus a bare con.close(). The close() calls used to sit on the happy path --
# inside the try in /analyse, after the query on every read endpoint -- so a
# query that raised never reached them. On SQLite that leaks nothing that
# matters; on the pooled Postgres path close() IS putconn(), so every failed
# request permanently removed one connection from a pool of five and five
# failures wedged the process. The context manager cannot be forgotten.
from .submissions_db import connection  # noqa: E402


# --------------------------------------------------------------------------
# Model loading
# --------------------------------------------------------------------------
_POLARITY_LABEL = {"N": "negative", "P": "positive", "X": "neutral"}


def _dump_aspect_polarity(per_aspect: Dict[str, str]) -> str:
    """Serialise the per-aspect verdicts for storage.

    Sorted keys and no whitespace, both deliberately: /stats matches these
    rows with `aspect_polarity LIKE '%"safety":"N"%'`, which is portable
    across SQLite and Postgres and needs the encoding to be exact. Anything
    that varies the separators -- json.dumps' default ", " and ": " included
    -- silently stops matching.
    """
    return json.dumps(per_aspect, sort_keys=True, separators=(",", ":"))


def _aspect_negative_like(aspect_key: str) -> str:
    """The LIKE pattern that finds a negative verdict for one aspect in a
    string written by _dump_aspect_polarity(). Defined next to the writer so
    the two cannot drift."""
    return '%"{}":"N"%'.format(aspect_key)


def _escape_like(value: str) -> str:
    """Neutralise LIKE metacharacters in a user-supplied search term.

    Used with `ESCAPE '\\'`. The backslash is escaped first, or it would
    escape the escapes added after it.
    """
    return (value.replace("\\", "\\\\")
                 .replace("%", "\\%")
                 .replace("_", "\\_"))

# Lazy singleton — loaded once on first request, reused for every subsequent
# one. Loading a PyTorch model at import time would crash the server on machines
# without torch installed; lazy loading lets the lexicon fallback take over.
_trained_model: Optional[object] = None  # TransformerPolarity (Method E) once loaded
_use_trained: Optional[bool] = None   # None = not yet determined

# Uvicorn runs every `def` handler in a worker thread, so concurrent requests
# reach _get_polarity_method() at the same time. _use_trained is only assigned
# AFTER the load returns, and the load takes seconds -- so without this lock
# every request arriving in that window took the same branch and started its
# own load. Measured: four concurrent cold-start requests produced eight
# _load() calls and four 500s ("Tensor.item() cannot be called on meta
# tensors"), plus one full copy of the RoBERTa weights per thread.
_model_lock = threading.Lock()


def _get_polarity_method() -> tuple:
    """
    Return (model_or_None, method_name).

    Method E -- the transformer plus the pipeline's correction rules. Falls
    back to the lexicon if torch is unavailable. Cached after the first call.

    This used to load Method F, the star-label fine-tune, and that was the
    API's accuracy problem. reports/method_f_safety_audit.json exists to argue
    against deploying it: F flips 55.3% of safety complaints to PRAISE, because
    it was trained on star ratings and most safety warnings sit inside 5-star
    reviews. Measured on the audit's own examples:

        "but don't bath in beach because it's dangerous."   F: P   E: N
        "but it is very risky."                             F: P   E: N
        "she's bad luck, ripped everyone off."              F: P   E: N

    Six post-hoc override rules had accumulated below to patch those
    inversions one phrase at a time. Both the cause and the patches are now
    gone: the per-aspect chain is polarity.aspect_polarity(), the same
    function aggregate.py calls, so the portal cannot contradict the
    dashboard built from the same reviews.
    """
    global _trained_model, _use_trained
    # Double-checked: the fast path stays lock-free once loaded, and only the
    # first callers serialise. Re-tested inside the lock because another
    # thread may have finished the load while this one waited.
    if _use_trained is not None:
        return _trained_model, ("E_transformer_rules" if _use_trained else "A_lexicon")
    with _model_lock:
        if _use_trained is not None:
            return _trained_model, ("E_transformer_rules" if _use_trained else "A_lexicon")
        try:
            # ROBERTA_MODEL + ROBERTA_LABELS, not the bare default. This
            # was the real bug in the first version of this fix:
            # TransformerPolarity() with no arguments defaults to MODEL_NAME
            # ("distilbert-base-uncased-finetuned-sst-2-english"), Method B --
            # the 2-class FILM-REVIEW model, in confidence-threshold mode. The
            # batch pipeline's actual deployed Method E (polarity.py,
            # score_corpus(): pol_final) is built from Method D's output --
            # ROBERTA_MODEL, 3-class, native neutral -- fed through
            # final_polarity(). Loading the wrong base model here meant the
            # docstring's claim two paragraphs up ("cannot contradict the
            # dashboard's numbers") was false: this endpoint was scoring
            # sentiment with the domain-mismatched film-review model the
            # project's own documentation names as a limitation, not the
            # tourism-appropriate one the published report is built from.
            from .polarity import TransformerPolarity, ROBERTA_MODEL, ROBERTA_LABELS
            _trained_model = TransformerPolarity(
                model_name=ROBERTA_MODEL, label_map=ROBERTA_LABELS)
            _trained_model._load()
            _use_trained = True
            print("  [api] polarity method: Method E "
                  "(transformer + correction rules) -- same as the pipeline")
        except Exception as exc:
            print("  [api] transformer failed to load ({}), "
                  "falling back to lexicon".format(exc))
            _use_trained = False
    return _trained_model, ("E_transformer_rules" if _use_trained else "A_lexicon")


# --------------------------------------------------------------------------
# Analysis logic
# --------------------------------------------------------------------------

def _analyse_text(text: str) -> tuple:
    """
    Segment one review and classify each piece.

    Returns (segments, method_name, truncated) where segments is a list of:
        segment_text    str
        aspects         list[str]        aspect keys with a match
        polarity        str              N / P / X -- segment level
        aspect_polarity dict[str, str]   the verdict per aspect
        polarity_score  float            lexicon score
        triggered_words list[str]        words that caused each aspect tag

    Two polarity fields, because the pipeline has two, and collapsing them
    into one was the bug this replaced. `polarity` is the segment-level
    Method E verdict -- the pol_final column in the corpus tables.
    `aspect_polarity` is what the dashboard actually counts: that verdict put
    through polarity.aspect_polarity() once per aspect. A sentence can be a
    safety complaint and a scenery compliment simultaneously, and only the
    second field can say so. Roll-ups use aspect_polarity; `polarity` stays
    because it is the value the corpus stores, so a reader checking a result
    against segments_scored.csv has the column they are looking for.
    """
    model, method = _get_polarity_method()
    results = []
    # MIN_SEGMENT_WORDS, not a hardcoded 3 -- this used to duplicate
    # segment.py's threshold by coincidence rather than by reference, which
    # is exactly the kind of thing that quietly drifts apart. It also used
    # to be the ONLY place this filter existed: the CLI engine in
    # analyse.py called split_into_segments() with no length filter at all,
    # so "though." (the second half of a contrast-split sentence) survived
    # as its own opinion unit there but not here -- two code paths meant to
    # be the same engine, disagreeing on what a review contains.
    pieces = [
        p for p in split_into_segments(text)
        if len(p.split()) >= MIN_SEGMENT_WORDS
    ]

    # A second bound behind ReviewRequest.text's max_length. One transformer
    # call per segment is the cost centre here, and the request holds a
    # worker thread for all of them: before either limit existed, a 144 KB
    # body produced 4,000 segments and occupied a worker for 353 seconds.
    # Truncating is reported rather than silent -- see AnalyseResponse.
    truncated = len(pieces) > MAX_SEGMENTS_PER_REVIEW
    if truncated:
        pieces = pieces[:MAX_SEGMENTS_PER_REVIEW]

    for piece in pieces:
        # Stage 3 -- what is this piece ABOUT?
        aspect_keys = tag_segment(piece)

        # Collect the trigger evidence for each matched aspect.
        triggers: List[str] = []
        for key in aspect_keys:
            triggers.extend(matched_terms(piece, key))

        # Stage 5 -- is the visitor happy or unhappy?
        lex_label, lex_score = lexicon_polarity(piece)

        if model is not None and aspect_keys:
            # Method E, segment level: the transformer reads the sentence and
            # final_polarity() applies the polite-request correction. Exactly
            # what score_corpus() writes to pol_final.
            model_label = model.predict([piece], verbose=False)[0]["label"]
            label, _ = final_polarity(piece, model_label, lex_label, lex_score)
        else:
            # Method A. Two cases reach here. Without the transformer this is
            # the documented lexicon fallback. With it, an untagged segment
            # has no aspect for the model's verdict to attach to -- and no
            # counterpart in the corpus either, since score_corpus() runs
            # with only_tagged=True. Its label is reported for completeness
            # and never reaches the summary.
            label = lex_label

        # The per-aspect correction chain -- safety recall, then site rule --
        # from polarity.py, the same call aggregate.py makes when it builds
        # the dashboard. Once per aspect, because that is the unit the rules
        # are defined on: a prohibition is neutralised for every aspect it is
        # tagged under, and the safety recall applies to the safety count
        # without touching what the same sentence says about the scenery.
        per_aspect: Dict[str, str] = {}
        for key in aspect_keys:
            per_aspect[key], _, _ = aspect_polarity(
                piece, key, label, lex_label)

        results.append({
            "segment_text": piece,
            "aspects": aspect_keys,
            "polarity": label,
            "aspect_polarity": per_aspect,
            "polarity_score": round(lex_score, 4),
            "triggered_words": sorted(set(triggers)),
        })

    return results, method, truncated


def _summarise(segments: List[Dict]) -> Dict[str, Optional[str]]:
    """
    Roll up per-aspect polarities to one verdict per aspect.

    Rule: if ANY segment is negative on this aspect, negative wins.
    Rationale: a safety warning inside a five-star review is the core
    finding of this project; suppressing it at the summary level would
    reproduce the exact blind spot the system exists to expose.

    Reads aspect_polarity, not the segment-level label. Reading the segment
    label meant a sentence tagged safety + scenery contributed the safety
    verdict to the scenery count.
    """
    summary: Dict[str, Optional[str]] = {k: None for k in C.ASPECTS}

    for seg in segments:
        for key, pol in (seg.get("aspect_polarity") or {}).items():
            if key not in summary:
                continue
            new_label = _POLARITY_LABEL.get(pol, "neutral")
            current = summary[key]
            if current is None:
                summary[key] = new_label
            elif current != "negative" and new_label == "negative":
                summary[key] = "negative"   # negative always wins
    return summary


# --------------------------------------------------------------------------
# FastAPI application
# --------------------------------------------------------------------------
app = FastAPI(
    title="LostinSriLanka Review API",
    description=(
        "Real-time aspect-based complaint analysis for Sri Lankan tourist reviews. "
        "POST a review to /analyse and get back which aspect (cleanliness, safety, "
        "roads, facilities, price, crowding, scenery) it touches and whether the "
        "visitor is complaining or praising."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Allow the static dashboard (and any local dev server) to call this API.
# Nothing in this repository calls this API from a browser: the built
# dashboard (dashboard/index.html) is fully static and contains no fetch(),
# no XMLHttpRequest and no reference to this port. The comment here used to
# claim otherwise, which is exactly the sentence that would justify keeping
# "*" through a review.
#
# "*" stays as the local-development default, because a wide-open origin on
# a laptop costs nothing. Set ALLOWED_ORIGINS (comma-separated) on any
# deploy and the wildcard is gone.
_origins_env = (os.environ.get("ALLOWED_ORIGINS") or "").strip()
ALLOWED_ORIGINS = ([o.strip() for o in _origins_env.split(",") if o.strip()]
                   if _origins_env else ["*"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------
# Pydantic models
# --------------------------------------------------------------------------
class ReviewRequest(BaseModel):
    """
    Every field here is stripped before it is measured.

    min_length counts characters as sent, so ten spaces used to satisfy
    `min_length=10` on text, and three spaces satisfied `min_length=2` on
    destination and district. Those requests returned 200, produced zero
    segments, and were written to the corpus as reviews -- inflating
    /stats.total_reviews with rows carrying no content at all.
    """

    text: str = Field(
        ...,
        min_length=10,
        max_length=MAX_TEXT_CHARS,
        description=(
            "The full review text. 10 to {:,} characters after "
            "trimming whitespace.".format(MAX_TEXT_CHARS)
        ),
        examples=["Kandy lake is polluted and the surrounding area is dirty."],
    )
    destination: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="Name of the place being reviewed.",
        examples=["Kandy Lake"],
    )
    district: str = Field(
        ...,
        min_length=2,
        max_length=60,
        description=(
            "Sri Lankan district the destination sits in. Must be one of the "
            "25 returned by GET /districts; matched case-insensitively and "
            "stored in its canonical spelling."
        ),
        examples=["Kandy"],
    )
    source: str = Field(
        default="user_submission",
        max_length=100,
        description="Where this review came from. Defaults to 'user_submission'.",
    )

    @field_validator("text", "destination", "district", "source", mode="before")
    @classmethod
    def _strip(cls, v):
        """Trim before the length rules are applied, so whitespace cannot
        stand in for content."""
        return v.strip() if isinstance(v, str) else v

    @field_validator("district")
    @classmethod
    def _known_district(cls, v: str) -> str:
        """Resolve to a canonical district name, or reject.

        /districts told callers to use its values and nothing enforced it, so
        {"district": "Neverland"} was accepted and stored. A submission filed
        under a district that does not exist cannot be aggregated with
        anything, which makes it unusable rather than merely untidy.
        """
        canonical = C.DISTRICT_LOOKUP.get(v.lower())
        if canonical is None:
            raise ValueError(
                "unknown district {!r} -- expected one of the 25 listed at "
                "GET /districts".format(v)
            )
        return canonical


class SegmentResult(BaseModel):
    segment_text: str
    aspects: List[str]
    polarity: str                     # N / P / X, segment level (= pol_final)
    polarity_label: str               # negative / positive / neutral
    aspect_polarity: Dict[str, str]   # per aspect, after the correction chain
    polarity_score: float             # lexicon score (informational)
    triggered_words: List[str]


class AnalyseResponse(BaseModel):
    review_id: str
    destination: str
    district: str
    submitted_at: str
    polarity_method: str        # which method scored this: E_transformer_rules or A_lexicon
    segments: List[SegmentResult]
    summary: Dict[str, Optional[str]]
    stored: bool
    # Returned once, never stored in plain form. It is what lets the person who
    # wrote a review withdraw it later without this project asking them for a
    # name or an email in order to prove it was theirs.
    manage_token: Optional[str] = None
    # True when the review carried more opinion units than
    # MAX_SEGMENTS_PER_REVIEW and the tail was not analysed. Reported rather
    # than silent, so a caller can tell a partial result from a complete one.
    truncated: bool = False


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------
@app.get("/health", tags=["Meta"])
def health():
    """Liveness probe. Returns 200, which polarity method is active, and
    which storage backend submissions are going to. Reports the SQLite file
    path only when that is the actual backend -- a Postgres DSN carries a
    password and must never be echoed back over this endpoint."""
    from .submissions_db import SUBMISSIONS_DB, active_backend
    backend = active_backend()
    _, method = _get_polarity_method()
    return {
        "status": "ok",
        "polarity_method": method,
        # trained_model_available() checks for the OLD Method F checkpoint
        # directory -- irrelevant since Method E does not use it. This
        # reports whether the ACTIVE method actually is the transformer, so
        # it stays true to what /analyse is really doing right now.
        "model_available": method == "E_transformer_rules",
        "submissions_backend": backend,
        "db": str(SUBMISSIONS_DB) if backend == "sqlite" else "postgres (Neon)",
    }


@app.get("/districts", tags=["Reference"])
def list_districts():
    """
    Return all 25 administrative districts of Sri Lanka. These are exactly
    the values POST /analyse accepts in its `district` field, matched
    case-insensitively.

    `in_corpus` marks the districts the research corpus actually covers.
    That is a statement about scraper reach, not about which districts a
    visitor may review -- this endpoint used to conflate the two and return
    only the 19 with data, while telling callers to submit one of its values.
    A place in Batticaloa had no correct answer.
    """
    covered = set(C.DISTRICT_CANON.values()) | {
        # Districts already spelled canonically in the corpus, so they never
        # needed an entry in DISTRICT_CANON.
        "Kandy", "Anuradhapura", "Polonnaruwa", "Kegalle", "Mannar",
        "Trincomalee", "Jaffna",
    }
    return {
        "districts": list(C.DISTRICTS),
        "count": len(C.DISTRICTS),
        "in_corpus": [n for n in C.DISTRICTS if n in covered],
    }


@app.get("/aspects", tags=["Reference"])
def list_aspects():
    """
    Return the seven aspects and their plain-English definitions.
    The `key` values appear in segment-level results and the summary.
    """
    return {
        "aspects": [
            {
                "key": key,
                "label": asp.label,
                "description": asp.description,
            }
            for key, asp in C.ASPECTS.items()
        ]
    }


# In-process cache — segments_scored.csv is ~38 MB; reading it on every
# request would be wasteful. Computed once on first call, reused thereafter.
_corpus_summary_cache: Optional[dict] = None
_corpus_summary_lock = threading.Lock()

_ASP_COLS = {
    "asp_safety":       ("safety",         "Safety"),
    "asp_price_value":  ("price_value",    "Price & Value"),
    "asp_cleanliness":  ("cleanliness",    "Cleanliness"),
    "asp_roads_access": ("roads_access",   "Roads & Access"),
    "asp_facilities":   ("facilities",     "Facilities"),
    "asp_crowd":        ("crowding_noise", "Crowding & Noise"),
    "asp_scenery":      ("scenery_nature", "Scenery & Nature"),
}


def _build_corpus_summary() -> dict:
    """Read segments_scored.csv and return the shape ReviewsPanel.jsx expects."""
    import pandas as pd

    path = C.DATA_PROCESSED / "segments_scored.csv"
    needed = (["review_id", "destination", "district", "n_aspects", "pol_final"]
              + list(_ASP_COLS.keys()))
    seg = pd.read_csv(path, usecols=needed)
    tagged = seg[seg["n_aspects"] > 0]

    aspects = []
    for col, (key, label) in _ASP_COLS.items():
        sub = tagged[tagged[col] == True]
        neg = int((sub["pol_final"] == "N").sum())
        pos = int((sub["pol_final"] == "P").sum())
        total = neg + pos
        rate = round(100 * neg / total, 1) if total else 0.0
        aspects.append({"key": key, "label": label,
                         "complaint_rate": rate,
                         "n_negative": neg, "n_positive": pos})

    # Worst districts for safety complaints.
    safety_tagged = tagged[tagged["asp_safety"] == True]
    safety_neg = safety_tagged[safety_tagged["pol_final"] == "N"]
    worst = (safety_neg.groupby("district")
                       .size()
                       .sort_values(ascending=False)
                       .head(3)
                       .reset_index(name="complaint_count"))
    worst_list = [{"district": r.district, "complaint_count": int(r.complaint_count)}
                  for r in worst.itertuples(index=False)]

    return {
        "total_reviews": int(seg["review_id"].nunique()),
        "destinations":  int(seg["destination"].nunique()),
        "districts":     int(seg["district"].nunique()),
        "aspects":       aspects,
        "worst_safety_districts": worst_list,
    }


@app.get("/corpus-summary", tags=["Reference"])
def corpus_summary():
    """
    Pre-computed aggregate statistics for the research corpus.

    Used by the Reviews panel sidebar to show complaint-rate bars and the
    worst-safety-districts ranking without a full database scan per request.
    Computed once from segments_scored.csv on first call and cached in-process.
    """
    global _corpus_summary_cache
    if _corpus_summary_cache is not None:
        return _corpus_summary_cache
    with _corpus_summary_lock:
        if _corpus_summary_cache is None:
            try:
                _corpus_summary_cache = _build_corpus_summary()
            except Exception as exc:
                raise HTTPException(
                    status_code=503,
                    detail="Could not read corpus: {}".format(exc))
    return _corpus_summary_cache


@app.post("/analyse", response_model=AnalyseResponse, tags=["Analysis"])
def analyse(req: ReviewRequest, request: Request):
    """
    Analyse a review text and return aspect-level complaint/praise labels.

    **What happens:**
    1. The text is split into opinion units (one per sentence / contrast clause).
    2. Each unit is tagged with the aspects it mentions (cleanliness, safety …).
    3. Each unit is scored per aspect: negative / positive / neutral.
    4. The result is stored in `user_submissions.db` and returned immediately.

    **Two polarity fields per segment.** `polarity` is the segment-level
    verdict, the same value the corpus stores as `pol_final`.
    `aspect_polarity` is that verdict after the per-aspect correction chain,
    and it is what `summary` and the dashboard's counts are built from. They
    differ whenever a sentence says different things about different aspects.

    **Polarity method (in priority order):**
    - `E_transformer_rules` — the same transformer + correction-rule pipeline
      the research dashboard is built from (src/travellens/polarity.py), so a
      review submitted here scores consistently with the published report.
      Measured against human labels in reports/polarity_accuracy_deployed.json.
    - `A_lexicon` — rule-based fallback used only if the transformer cannot be
      loaded. The `polarity_method` field in the response tells you which one
      scored this request.

    Rate limited per IP; see RATE_LIMIT_REQUESTS.
    """
    client_ip = request.client.host if request.client else "unknown"
    if _rate_limited(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Too many submissions. Limit is {} per {} seconds.".format(
                RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SECONDS),
        )

    # Run the analysis.
    raw_segments, method, truncated = _analyse_text(req.text)
    summary = _summarise(raw_segments)

    # Build a stable, sortable ID: usr_<UTC date>_<8-char uuid fragment>
    now_utc = datetime.now(timezone.utc)
    review_id = "usr_{}_{}" .format(
        now_utc.strftime("%Y%m%d_%H%M%S"),
        uuid.uuid4().hex[:8],
    )
    submitted_at = now_utc.isoformat()

    # Persist to the submissions database.
    #
    # Only if there is something to persist. A review that yields no opinion
    # units carries no analysis, and storing it added a row to the corpus and
    # a count to /stats.total_reviews in exchange for nothing. The caller
    # still gets its (empty) result back, and `stored` says what happened.
    # Issued whether or not storage succeeds, so the response shape is stable;
    # it is only useful when `stored` is true.
    manage_token, manage_token_hash = _new_manage_token()

    stored = False
    if raw_segments:
        try:
            with connection() as con:
                con.execute(
                    "INSERT INTO user_reviews "
                    "(review_id, destination, district, raw_text, source, "
                    " submitted_at, manage_token_hash) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (review_id, req.destination, req.district,
                     req.text, req.source, submitted_at, manage_token_hash),
                )
                for i, seg in enumerate(raw_segments):
                    con.execute(
                        "INSERT INTO user_segments "
                        "(review_id, seg_index, segment_text, aspects, "
                        " polarity, aspect_polarity, polarity_score, triggered_words) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            review_id, i, seg["segment_text"],
                            json.dumps(seg["aspects"]),
                            seg["polarity"],
                            _dump_aspect_polarity(seg["aspect_polarity"]),
                            seg["polarity_score"],
                            json.dumps(seg["triggered_words"]),
                        ),
                    )
                con.commit()
            stored = True
        except Exception as exc:
            # Analysis result is still returned even if storage fails.
            print("  [warn] could not store review: {}".format(exc))

    # Shape the response.
    segment_results = [
        SegmentResult(
            segment_text=s["segment_text"],
            aspects=s["aspects"],
            polarity=s["polarity"],
            polarity_label=_POLARITY_LABEL.get(s["polarity"], "neutral"),
            aspect_polarity={
                k: _POLARITY_LABEL.get(v, "neutral")
                for k, v in s["aspect_polarity"].items()
            },
            polarity_score=s["polarity_score"],
            triggered_words=s["triggered_words"],
        )
        for s in raw_segments
    ]

    return AnalyseResponse(
        review_id=review_id,
        destination=req.destination,
        district=req.district,
        submitted_at=submitted_at,
        polarity_method=method,
        segments=segment_results,
        summary=summary,
        stored=stored,
        manage_token=manage_token if stored else None,
        truncated=truncated,
    )


@app.get("/reviews", tags=["Submissions"])
def list_reviews(
    district: Optional[str] = Query(None, description="Filter by district"),
    destination: Optional[str] = Query(None, description="Filter by destination"),
    limit: int = Query(50, ge=1, le=500, description="Max results to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """
    List user-submitted reviews, newest first.

    Does NOT return the full segment analysis — use GET /reviews/{review_id}
    for the complete breakdown.
    """
    clauses, params = [], []
    if district:
        clauses.append("district = ?")
        params.append(district)
    if destination:
        # ESCAPE, because the caller's value goes into a LIKE pattern and
        # LIKE metacharacters are live inside it. `?destination=%` matched
        # every row in the table, and a destination whose real name contains
        # an underscore matched anything with a character in that position.
        clauses.append("destination LIKE ? ESCAPE '\\'")
        params.append("%{}%".format(_escape_like(destination)))

    # A withdrawn review is invisible to every read. Applied as a clause on the
    # shared WHERE rather than filtered in Python, so the count and the page
    # agree -- a total that includes rows the listing omits is worse than
    # either number alone.
    clauses.append("withdrawn_at IS NULL")

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with connection() as con:
        rows = con.execute(
            "SELECT review_id, destination, district, source, submitted_at, "
            "       length(raw_text) AS text_length "
            "FROM user_reviews {} "
            "ORDER BY submitted_at DESC "
            "LIMIT ? OFFSET ?".format(where),
            params + [limit, offset],
        ).fetchall()
        total = con.execute(
            "SELECT COUNT(*) FROM user_reviews {}".format(where), params
        ).fetchone()[0]

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "reviews": [dict(r) for r in rows],
    }


@app.get("/reviews/{review_id}", tags=["Submissions"])
def get_review(review_id: str):
    """
    Return one submitted review with its full segment-level analysis.
    """
    with connection() as con:
        rev = con.execute(
            "SELECT * FROM user_reviews WHERE review_id = ? "
            "AND withdrawn_at IS NULL", (review_id,)
        ).fetchone()
        if not rev:
            raise HTTPException(status_code=404, detail="Review not found")

        segs = con.execute(
            "SELECT seg_index, segment_text, aspects, polarity, "
            "       aspect_polarity, polarity_score, triggered_words "
            "FROM user_segments WHERE review_id = ? ORDER BY seg_index",
            (review_id,),
        ).fetchall()

    # Deserialise the JSON columns.
    segments = []
    for s in segs:
        d = dict(s)
        d["aspects"] = json.loads(d["aspects"])
        d["triggered_words"] = json.loads(d["triggered_words"])
        d["polarity_label"] = _POLARITY_LABEL.get(d["polarity"], "neutral")
        # NULL for rows written before aspect_polarity existed. Falling back
        # to the segment label reproduces exactly what those rows meant when
        # they were written, rather than inventing a per-aspect breakdown
        # that was never computed. Run scripts/42_rescore_submissions.py to
        # replace the fallback with real per-aspect verdicts.
        raw = d.get("aspect_polarity")
        if raw:
            d["aspect_polarity"] = json.loads(raw)
            d["rescored"] = True
        else:
            d["aspect_polarity"] = {a: d["polarity"] for a in d["aspects"]}
            d["rescored"] = False
        segments.append(d)

    # Rebuild the per-aspect summary from the stored segments.
    summary = _summarise(segments)

    return {
        **dict(rev),
        "segments": segments,
        "summary": summary,
    }


@app.get("/stats", tags=["Submissions"])
def submission_stats():
    """
    High-level counts for the user submission corpus.
    Returns complaint rates per aspect across all user-submitted reviews.

    Complaints are counted from `aspect_polarity`, the per-aspect verdict, so
    these rates mean the same thing as the dashboard's. Counting the
    segment-level label instead credited a safety complaint to every other
    aspect the same sentence mentioned.
    """
    keys = list(C.ASPECTS.keys())

    # ONE query, not sixteen. This used to run COUNT(*) once per aspect
    # (tagged) and once again (negative) in a Python loop -- 14 round trips,
    # plus 2 more for the totals. Locally, against SQLite on the same
    # machine, that is free. Against Neon over a real network it measured
    # 8+ seconds for a 34-row table -- almost entirely round-trip latency,
    # not query cost, since a single one of those queries runs in ~0.3s.
    # Every aspect's tagged/negative count is now one SUM(CASE ...) pair in
    # a single SELECT, portable across both backends without change.
    case_pairs = []
    params: List[str] = []
    for key in keys:
        case_pairs.append(
            "SUM(CASE WHEN aspects LIKE ? THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN aspect_polarity LIKE ? THEN 1 ELSE 0 END)"
        )
        params.extend(['%"{}"%'.format(key), _aspect_negative_like(key)])

    with connection() as con:
        total_reviews = con.execute(
            "SELECT COUNT(*) FROM user_reviews WHERE withdrawn_at IS NULL"
        ).fetchone()[0]
        row = con.execute(
            # Joined to user_reviews so a withdrawn review's segments leave
            # the complaint rates too. Counting segments alone would withdraw
            # the review from every listing while its opinions kept driving
            # every figure on the page.
            "SELECT COUNT(*), "
            "SUM(CASE WHEN aspect_polarity IS NULL THEN 1 ELSE 0 END), "
            "{} FROM user_segments s "
            "JOIN user_reviews r ON r.review_id = s.review_id "
            "WHERE r.withdrawn_at IS NULL".format(", ".join(case_pairs)),
            tuple(params),
        ).fetchone()

    total_segments = row[0] or 0
    unscored = row[1] or 0
    per_aspect = {}
    for i, key in enumerate(keys):
        tagged = row[2 + i * 2] or 0
        negative = row[3 + i * 2] or 0
        per_aspect[key] = {
            "label": C.ASPECTS[key].label,
            "tagged_segments": tagged,
            "complaints": negative,
            "complaint_rate": round(negative / tagged, 3) if tagged else None,
        }

    out = {
        "total_reviews": total_reviews,
        "total_segments": total_segments,
        "per_aspect": per_aspect,
    }
    # Rows written before per-aspect storage existed have no verdicts to
    # count, so they are absent from `complaints` above. Saying so is the
    # difference between a rate that is low and a rate that is incomplete;
    # scripts/42_rescore_submissions.py clears this to zero.
    if unscored:
        out["segments_awaiting_rescore"] = unscored
        out["note"] = (
            "{} segment(s) predate per-aspect scoring and contribute to "
            "tagged_segments but not to complaints. Run "
            "scripts/42_rescore_submissions.py to score them.".format(unscored)
        )
    return out



@app.get("/unmatched", tags=["Submissions"])
def unmatched_segments(limit: int = Query(100, ge=1, le=1000)):
    """
    Segments that matched NONE of the seven tracked aspects.

    Why this exists
    ----------------
    A test submission about Kandy contained "some souvenir sellers were
    overly persistent, especially when they kept following us" -- a real,
    common complaint (touting / vendor pressure) that fits none of the seven
    aspects. The right response to one example is not to guess at a fix; it
    is to see whether the pattern repeats once real reviews arrive. This
    endpoint is that instrument: every unmatched segment is already stored
    (aspects = '[]'), so nothing needed capturing, only surfacing.

    A cluster here over time is the evidence for adding a trigger, widening
    an aspect, or adding an eighth category -- not one review, and not a
    guess.
    """
    with connection() as con:
        rows = con.execute(
            "SELECT s.segment_text, s.review_id, r.destination, r.district, "
            "       r.submitted_at "
            "FROM user_segments s JOIN user_reviews r ON r.review_id = s.review_id "
            "WHERE s.aspects = '[]' AND r.withdrawn_at IS NULL "
            "ORDER BY r.submitted_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        # Both counts in one round trip rather than two -- the same latency
        # argument as /stats, just a smaller version of it.
        totals = con.execute(
            "SELECT COUNT(*), "
            "SUM(CASE WHEN s.aspects = '[]' THEN 1 ELSE 0 END) "
            "FROM user_segments s "
            "JOIN user_reviews r ON r.review_id = s.review_id "
            "WHERE r.withdrawn_at IS NULL"
        ).fetchone()
    total_segments = totals[0] or 0
    total_unmatched = totals[1] or 0

    return {
        "total_segments": total_segments,
        "total_unmatched": total_unmatched,
        "unmatched_rate": (round(total_unmatched / total_segments, 3)
                          if total_segments else None),
        "note": ("A segment lands here when it carries an opinion but matches "
                "none of the seven aspects -- distinct from a neutral/factual "
                "segment, which DOES match an aspect. Recurring language "
                "across many rows is the signal to act on, not any single row."),
        "segments": [dict(r) for r in rows],
    }


# --------------------------------------------------------------------------
# Contributor corrections and stories
#
# Both of these take content from anonymous visitors, and BOTH are kept out of
# every published figure. The reasons differ and are worth stating separately.
#
# Corrections are labels. This project already has a documented near-miss where
# labels of the wrong provenance were about to be reported as inter-annotator
# agreement (see src/travellens/agreement.py), and a drive-by correction from
# an unknown visitor is weaker evidence still than an assistant's pass: there
# is no annotation guideline behind it, no second reader, and no way to ask
# what they meant. So corrections are stored with labelled_by='contributor',
# a value agreement.py does not recognise and therefore REFUSES -- which is
# the intended behaviour, not an oversight. They are a queue for a human to
# read, and a map of where the pipeline looks wrong to the people it describes.
# They are not gold labels and they change no number by themselves.
#
# Stories are media. The project's existing rule is that storyboard media is
# displayed and never counted (tests/test_media_separation.py). A visitor's
# blog post is the same kind of object as a news article about the same place,
# so it inherits the same rule: user_stories is never read by aggregation and
# never contributes to a complaint rate.
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# Ownership without accounts
#
# There is no sign-in here and there should not be: the portal asks for no name
# and no email, and adding a login to support an edit button would collect more
# about a contributor than the review itself does.
#
# So editing rights travel with a token issued once, at creation, and never
# stored. Only its SHA-256 hash is kept, so a copy of this database does not
# let anybody edit or delete anyone else's content. The alternative -- an open
# PATCH/DELETE keyed on the id alone -- would let any caller who can read a
# listing rewrite every row in it.
# --------------------------------------------------------------------------
import hashlib  # noqa: E402
import hmac  # noqa: E402
import secrets  # noqa: E402


def _new_manage_token() -> tuple:
    """Returns (token, hash). The token is shown to the author exactly once."""
    token = secrets.token_urlsafe(24)
    return token, hashlib.sha256(token.encode()).hexdigest()


def _token_matches(token: Optional[str], stored_hash: Optional[str]) -> bool:
    """Constant-time comparison, so a caller cannot narrow the token by timing.

    A row with no stored hash was created before tokens existed. It is
    unmanageable rather than open to everyone: refusing is the safe direction,
    and the alternative would make every historical row editable by anybody.
    """
    if not token or not stored_hash:
        return False
    given = hashlib.sha256(token.encode()).hexdigest()
    return hmac.compare_digest(given, stored_hash)


def _require_token(request: Request, stored_hash: Optional[str], what: str):
    token = (request.headers.get("X-Manage-Token")
             or request.query_params.get("manage_token"))
    if not _token_matches(token, stored_hash):
        raise HTTPException(
            status_code=403,
            detail=("This {} can only be changed with the management token "
                    "returned when it was created. Rows created before tokens "
                    "existed cannot be changed at all.".format(what)))


_VERDICTS = {"complaint": "N", "praise": "P", "factual": "X",
             "N": "N", "P": "P", "X": "X"}
NOT_ABOUT_THIS = "not_about_this"


class CorrectionRequest(BaseModel):
    """One visitor disagreeing with one category on one sentence."""

    review_id: str = Field(..., min_length=4, max_length=64)
    seg_index: int = Field(..., ge=0)
    aspect: str = Field(
        ...,
        description="Which of the seven categories this is about.",
    )
    human_verdict: str = Field(
        ...,
        description=(
            "What the visitor says it really is: 'complaint', 'praise', "
            "'factual', or 'not_about_this' when the category does not apply "
            "to the sentence at all."
        ),
    )
    note: Optional[str] = Field(default=None, max_length=500)

    @field_validator("aspect")
    @classmethod
    def _known_aspect(cls, v: str) -> str:
        if v not in C.ASPECTS:
            raise ValueError(
                "unknown aspect {!r} -- expected one of {}".format(
                    v, sorted(C.ASPECTS)))
        return v

    @field_validator("human_verdict")
    @classmethod
    def _known_verdict(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v == NOT_ABOUT_THIS:
            return v
        if v not in _VERDICTS:
            raise ValueError(
                "unknown verdict {!r} -- expected complaint, praise, factual "
                "or {}".format(v, NOT_ABOUT_THIS))
        return _VERDICTS[v]


@app.post("/corrections", tags=["Corrections"], status_code=201)
def submit_correction(req: CorrectionRequest, request: Request):
    """
    Record that the analysis got a sentence wrong.

    Stored against the segment it corrects, alongside what the pipeline said,
    so the pair can be read later. Nothing recomputes: no scorecard, no
    complaint rate and no /stats figure moves because of a correction. See
    GET /corrections for what the queue is for.
    """
    if _rate_limited(request.client.host if request.client else "unknown"):
        raise HTTPException(status_code=429, detail="Too many submissions.")

    now_utc = datetime.now(timezone.utc)
    correction_id = "cor_{}_{}".format(
        now_utc.strftime("%Y%m%d_%H%M%S"), uuid.uuid4().hex[:8])

    with connection() as con:
        seg = con.execute(
            "SELECT segment_text, aspects, aspect_polarity FROM user_segments "
            "WHERE review_id = ? AND seg_index = ?",
            (req.review_id, req.seg_index),
        ).fetchone()
        if seg is None:
            raise HTTPException(
                status_code=404,
                detail="No segment {} on review {}".format(
                    req.seg_index, req.review_id))

        # What the pipeline said about THIS aspect on THIS segment, so the
        # correction is stored as a pair rather than as a bare opinion.
        tagged = json.loads(seg["aspects"] or "[]")
        if req.aspect in tagged:
            per_aspect = json.loads(seg["aspect_polarity"] or "{}")
            machine = per_aspect.get(req.aspect)
        else:
            machine = "not_tagged"

        con.execute(
            "INSERT INTO user_corrections "
            "(correction_id, review_id, seg_index, segment_text, aspect, "
            " machine_verdict, human_verdict, labelled_by, note, submitted_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (correction_id, req.review_id, req.seg_index, seg["segment_text"],
             req.aspect, machine, req.human_verdict, "contributor",
             (req.note or "").strip() or None, now_utc.isoformat()),
        )
        con.commit()

    return {
        "correction_id": correction_id,
        "recorded": True,
        "machine_verdict": machine,
        "human_verdict": req.human_verdict,
        "note": ("Recorded for review. Corrections do not change any published "
                 "figure on their own -- they are a queue for a person to "
                 "read."),
    }


@app.get("/corrections", tags=["Corrections"])
def list_corrections(limit: int = Query(100, ge=1, le=1000),
                     aspect: Optional[str] = Query(None)):
    """
    The correction queue: where visitors say the pipeline read them wrong.

    This is the instrument /unmatched is, pointed at a different failure. An
    unmatched segment says "no category fits"; a correction says "this
    category fits badly". Both are evidence for a change to the lexicon, the
    taxonomy or an aspect's definition -- and neither is that change.

    `disagreements` counts only the rows where the visitor and the pipeline
    actually differ, because a contributor confirming a correct call is worth
    storing and is not evidence of a problem.
    """
    sql = ("SELECT correction_id, review_id, seg_index, segment_text, aspect, "
           "       machine_verdict, human_verdict, note, submitted_at "
           "FROM user_corrections ")
    params: List = []
    if aspect:
        if aspect not in C.ASPECTS:
            raise HTTPException(status_code=400,
                                detail="unknown aspect {!r}".format(aspect))
        sql += "WHERE aspect = ? "
        params.append(aspect)
    sql += "ORDER BY submitted_at DESC LIMIT ?"
    params.append(limit)

    with connection() as con:
        rows = [dict(r) for r in con.execute(sql, tuple(params)).fetchall()]
        by_aspect = con.execute(
            "SELECT aspect, COUNT(*) AS n, "
            "SUM(CASE WHEN machine_verdict IS NULL "
            "         OR machine_verdict <> human_verdict THEN 1 ELSE 0 END) "
            "AS disagreements "
            "FROM user_corrections GROUP BY aspect"
        ).fetchall()

    return {
        "total": sum(int(r["n"]) for r in by_aspect),
        "by_aspect": {r["aspect"]: {"corrections": int(r["n"]),
                                    "disagreements": int(r["disagreements"] or 0)}
                      for r in by_aspect},
        "provenance": "contributor",
        "note": ("These are NOT gold labels. They carry labelled_by="
                 "'contributor', which src/travellens/agreement.py refuses, "
                 "so they cannot become an accuracy or agreement figure "
                 "without a deliberate human annotation pass."),
        "corrections": rows,
    }


class StoryRequest(BaseModel):
    """A visitor's write-up about a place. Displayed, never counted."""

    title: str = Field(..., min_length=3, max_length=200)
    body: str = Field(..., min_length=30, max_length=20000)
    url: Optional[str] = Field(default=None, max_length=500)
    destination: Optional[str] = Field(default=None, max_length=200)
    district: Optional[str] = Field(default=None, max_length=60)
    author: Optional[str] = Field(default=None, max_length=100)

    @field_validator("title", "body", "url", "destination", "district",
                     "author", mode="before")
    @classmethod
    def _strip_story(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("url")
    @classmethod
    def _http_only(cls, v):
        """Only http(s). A stored javascript: or data: URL becomes an attack
        the moment any page renders it as a link."""
        if v and not v.lower().startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return v or None

    @field_validator("district")
    @classmethod
    def _known_district_optional(cls, v):
        if not v:
            return None
        canonical = C.DISTRICT_LOOKUP.get(v.lower())
        if canonical is None:
            raise ValueError("unknown district {!r}".format(v))
        return canonical


@app.post("/stories", tags=["Storyboard"], status_code=201)
def submit_story(req: StoryRequest, request: Request):
    """
    Add a story or blog post to the storyboard.

    Storyboard content is displayed beside a destination and never enters a
    calculation -- the rule the collected news and video items already follow
    (tests/test_media_separation.py). A visitor's write-up is the same kind of
    object, so it inherits the same rule: this text is never segmented, never
    tagged and never counted in any complaint rate.
    """
    if _rate_limited(request.client.host if request.client else "unknown"):
        raise HTTPException(status_code=429, detail="Too many submissions.")

    now_utc = datetime.now(timezone.utc)
    story_id = "sty_{}_{}".format(
        now_utc.strftime("%Y%m%d_%H%M%S"), uuid.uuid4().hex[:8])

    token, token_hash = _new_manage_token()
    with connection() as con:
        con.execute(
            "INSERT INTO user_stories "
            "(story_id, title, body, url, destination, district, author, "
            " submitted_at, manage_token_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (story_id, req.title, req.body, req.url, req.destination,
             req.district, req.author or None, now_utc.isoformat(), token_hash),
        )
        con.commit()

    return {"story_id": story_id, "published": True,
            "manage_token": token,
            "manage_note": ("Keep this to edit or delete the story later. It "
                            "is shown once and is not recoverable -- only its "
                            "hash is stored."),
            "note": "Displayed on the storyboard. Never counted in any figure."}


@app.get("/stories", tags=["Storyboard"])
def list_stories(destination: Optional[str] = Query(None),
                 district: Optional[str] = Query(None),
                 limit: int = Query(50, ge=1, le=500),
                 offset: int = Query(0, ge=0)):
    """Stories visitors have added, newest first."""
    sql = ("SELECT story_id, title, body, url, destination, district, author, "
           "submitted_at FROM user_stories")
    where, params = [], []
    if destination:
        where.append("destination = ?")
        params.append(destination)
    if district:
        where.append("district = ?")
        params.append(district)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY submitted_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with connection() as con:
        rows = [dict(r) for r in con.execute(sql, tuple(params)).fetchall()]
        total = con.execute("SELECT COUNT(*) FROM user_stories").fetchone()[0]

    return {"total": total, "count": len(rows), "stories": rows,
            "note": "Storyboard content. Displayed, never counted."}


# --------------------------------------------------------------------------
# The two pages, served from this same process
#
# Until now the system was three things to start: this API, a static server for
# dashboard/index.html, and another for portal/index.html. That is fine while
# developing and wrong to hand to anybody -- the portal calls the API, so a
# reader who opens the file directly gets a page that looks finished and does
# nothing, with the reason buried in a browser console.
#
# Serving both from here makes the whole system one process on one port, and
# removes the CORS question entirely: same origin, no preflight, no
# ALLOWED_ORIGINS to get wrong on a deploy.
#
# Mounted AFTER every API route, and on explicit paths rather than as a
# catch-all, so nothing here can shadow /analyse, /stats or /docs.
# --------------------------------------------------------------------------
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse  # noqa: E402

_PAGES = {
    "portal": C.ROOT / "portal" / "index.html",
    "dashboard": C.ROOT / "dashboard" / "index.html",
}

_BUILD_HINT = {
    "portal": "python scripts/45_build_portal.py",
    "dashboard": "python scripts/08_build_dashboard.py",
}


def _page(name: str):
    """Serve a built page, or say plainly which command builds it.

    A missing page is a build that was not run, not a server fault. Returning
    the command is the difference between a 404 and an answer.
    """
    path = _PAGES[name]
    if path.exists():
        # no-store, not no-cache. Both files are rebuilt in place under the
        # same URL, and a stale copy is indistinguishable from a rebuild that
        # did not happen -- the failure preflight's timestamp check exists to
        # catch. `no-cache` only asks for revalidation and was observed still
        # serving a previous build after a rebuild; `no-store` is the one that
        # means what is wanted here.
        return HTMLResponse(
            path.read_text("utf-8"),
            media_type="text/html",
            headers={
                "Cache-Control": "no-store, must-revalidate",
                "Pragma": "no-cache",
            })
    return HTMLResponse(
        "<h1>The {name} has not been built yet</h1>"
        "<p>Run <code>{cmd}</code> from the travellens directory, then "
        "reload.</p>".format(name=name, cmd=_BUILD_HINT[name]),
        status_code=503)


@app.get("/", include_in_schema=False)
def root(request: Request):
    """Land on the portal, at the path its own links assume.

    Redirected rather than served in place: the portal links to the dashboard
    as ../dashboard/index.html, which only resolves if the portal is itself at
    /portal/index.html. Serving the same bytes at / would give a page whose
    only outbound link 404s.

    Built from root_path so this app can be mounted under a prefix -- the
    gateway at the repository root mounts it at /travellens to put all three
    applications on one origin. A literal "/portal/index.html" would leave the
    mount and land on the gateway root, a 404 that looks like this app is
    broken rather than mis-addressed.
    """
    prefix = request.scope.get("root_path", "")
    return RedirectResponse(prefix + "/portal/index.html")


@app.get("/portal/index.html", include_in_schema=False)
@app.get("/portal", include_in_schema=False)
def portal_page():
    return _page("portal")


@app.get("/dashboard/index.html", include_in_schema=False)
@app.get("/dashboard", include_in_schema=False)
def dashboard_page():
    return _page("dashboard")


class StoryUpdate(BaseModel):
    """Fields a story's author may change. Anything omitted is left alone."""

    title: Optional[str] = Field(default=None, min_length=3, max_length=200)
    body: Optional[str] = Field(default=None, min_length=30, max_length=20000)
    url: Optional[str] = Field(default=None, max_length=500)
    destination: Optional[str] = Field(default=None, max_length=200)
    district: Optional[str] = Field(default=None, max_length=60)
    author: Optional[str] = Field(default=None, max_length=100)

    @field_validator("title", "body", "url", "destination", "district",
                     "author", mode="before")
    @classmethod
    def _strip_update(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("url")
    @classmethod
    def _http_only_update(cls, v):
        if v and not v.lower().startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return v

    @field_validator("district")
    @classmethod
    def _known_district_update(cls, v):
        if not v:
            return v
        canonical = C.DISTRICT_LOOKUP.get(v.lower())
        if canonical is None:
            raise ValueError("unknown district {!r}".format(v))
        return canonical


@app.patch("/stories/{story_id}", tags=["Storyboard"])
def update_story(story_id: str, req: StoryUpdate, request: Request):
    """Edit a story you wrote. Requires the token issued when it was created.

    A partial update: fields you leave out keep their current values, so
    correcting a typo does not require resending the whole story.
    """
    fields = {k: v for k, v in req.model_dump(exclude_unset=True).items()
              if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="nothing to change")

    with connection() as con:
        row = con.execute(
            "SELECT manage_token_hash FROM user_stories WHERE story_id = ?",
            (story_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="no such story")
        _require_token(request, row["manage_token_hash"], "story")

        sets = ", ".join("{} = ?".format(k) for k in fields)
        params = list(fields.values())
        params.append(datetime.now(timezone.utc).isoformat())
        params.append(story_id)
        con.execute("UPDATE user_stories SET {}, updated_at = ? "
                    "WHERE story_id = ?".format(sets), tuple(params))
        con.commit()
        after = con.execute(
            "SELECT story_id, title, body, url, destination, district, author,"
            " submitted_at, updated_at FROM user_stories WHERE story_id = ?",
            (story_id,)).fetchone()
    return {"updated": sorted(fields), "story": dict(after)}


@app.delete("/stories/{story_id}", tags=["Storyboard"])
def delete_story(story_id: str, request: Request):
    """Remove a story you wrote. Requires its management token.

    A real delete, unlike a review: a story is display-only content that never
    entered a calculation, so removing it changes no published figure and
    leaves nothing orphaned.
    """
    with connection() as con:
        row = con.execute(
            "SELECT manage_token_hash FROM user_stories WHERE story_id = ?",
            (story_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="no such story")
        _require_token(request, row["manage_token_hash"], "story")
        con.execute("DELETE FROM user_stories WHERE story_id = ?", (story_id,))
        con.commit()
    return {"deleted": story_id}


@app.post("/reviews/{review_id}/withdraw", tags=["Submissions"])
def withdraw_review(review_id: str, request: Request):
    """Withdraw a review you submitted. Requires its management token.

    Marked withdrawn, not deleted, and the difference is deliberate. A review
    is evidence; a DELETE would orphan its segments and silently move every
    figure derived from them, with no record that anything had been there.
    Withdrawn rows are excluded from every read and every count, and stay on
    disk.
    """
    with connection() as con:
        row = con.execute(
            "SELECT manage_token_hash, withdrawn_at FROM user_reviews "
            "WHERE review_id = ?", (review_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="no such review")
        _require_token(request, row["manage_token_hash"], "review")
        if row["withdrawn_at"]:
            return {"review_id": review_id, "withdrawn": True,
                    "withdrawn_at": row["withdrawn_at"],
                    "note": "already withdrawn"}
        when = datetime.now(timezone.utc).isoformat()
        con.execute("UPDATE user_reviews SET withdrawn_at = ? "
                    "WHERE review_id = ?", (when, review_id))
        con.commit()
    return {"review_id": review_id, "withdrawn": True, "withdrawn_at": when,
            "note": ("Excluded from every listing and every count. The row is "
                     "kept, because deleting it would change published figures "
                     "with no record that it had existed.")}
