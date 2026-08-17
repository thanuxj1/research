# Line-level patches
**IT22629180 · apply in this order**

Each patch is small, independently reviewable, and closes a specific audit finding.

---

## P1 — `scripts/ablation_study.py` will not run (audit m1)

The module is `app.db.session`, not `app.db.database`.

```diff
-from app.db.database import SessionLocal
+from app.db.session import SessionLocal
```

Same file: the ablation aggregates on `location_name`, which holds **city** names, while
the map aggregates on **district**. The two are not the same unit, so the ablation is
currently not an ablation of the scoring you ship.

```diff
-        d = getattr(r, "location_name", None)
-        if not d:
-            continue
+        d = resolve_district(r)      # same point-in-polygon path district_engine uses
+        if not d or d.lower() in {"sri lanka", "national"}:
+            continue                 # national-scope records are not district evidence
```

---

## P2 — Freeze the corpus (audit M1, blocks reproducibility)

`app/main.py` launches a scraper subprocess on every startup and schedules a daily 02:00
collection, so the database mutates under your evaluation.

```diff
 @app.on_event("startup")
 def start_automated_systems():
     global _scheduler
+
+    # RESEARCH_MODE freezes the corpus so that reported results are reproducible.
+    # Set RESEARCH_MODE=true in .env for every evaluation run.
+    if os.getenv("RESEARCH_MODE", "").lower() == "true":
+        print("[RESEARCH_MODE] Automated collection disabled — corpus is frozen.")
+        return
+
     if _scheduler is None:
```

Add to `.env.example`:

```
# Disables all automated collection so evaluation runs against a frozen corpus.
RESEARCH_MODE=false
```

Snapshot script — run before every evaluation and cite the hash in the thesis:

```python
# backend/scripts/freeze_corpus.py
import hashlib, json, datetime as dt
from app.db.session import SessionLocal
from app.db.models import Report

FIELDS = ["id", "source", "url", "title", "content", "is_scam", "scam_type",
          "risk_level", "latitude", "longitude", "location_name",
          "source_weight", "published_at", "has_publish_date",
          "geocode_confidence", "created_at"]

db = SessionLocal()
rows = [{f: (str(getattr(r, f)) if getattr(r, f) is not None else None)
         for f in FIELDS}
        for r in db.query(Report).order_by(Report.id).all()]
db.close()

payload = "\n".join(json.dumps(r, sort_keys=True) for r in rows)
digest = hashlib.sha256(payload.encode()).hexdigest()[:12]
name = f"corpus_v1_{dt.date.today()}_sha256-{digest}.jsonl"
open(name, "w", encoding="utf-8").write(payload)
print(f"{len(rows)} records -> {name}")
print(f"Cite this hash in the thesis: sha256:{digest}")
```

---

## P3 — Enforce the canonical taxonomy at write time (audit M7)

`scam_taxonomy.py` defines the canonical keys but nothing calls `normalise()` on insert, so
the DB carries a fifth vocabulary and `newswire` / `newswire_lk` are counted as two outlets.

In **every** ingestion path (`ingest_reviews_csv.py`, `import_all_reviews.py`,
`scrape_sl_news_v3.py`, all `collectors/*.py`, `continuous_runner.py`):

```diff
+from app.core.scam_taxonomy import normalise as normalise_scam_type
+from app.ml.source_weights import normalise_source_key
...
     report = Report(
-        scam_type=raw_scam_type,
-        source=raw_source,
+        scam_type=normalise_scam_type(raw_scam_type),
+        source=normalise_source_key(raw_source),
```

Add the source alias map to `source_weights.py`:

```python
SOURCE_ALIASES = {
    "newswire_lk": "newswire",
    "newswire.lk": "newswire",
    "adaderana.lk": "adaderana",
    "dailymirror.lk": "daily_mirror",
    "sundaytimes.lk": "sunday_times",
    "newsfirst.lk": "newsfirst",
    "tripadvisor_csv": "tripadvisor",
    "dataset_csv": "tripadvisor",
}

def normalise_source_key(raw: str | None) -> str:
    k = (raw or "unknown").strip().lower()
    return SOURCE_ALIASES.get(k, k)
```

Migration for existing rows, then a test that keeps it true:

```python
# backend/tests/test_taxonomy_enforced.py
from app.core.scam_taxonomy import CANONICAL_SCAM_TYPES
from app.db.session import SessionLocal
from app.db.models import Report

def test_all_scam_types_are_canonical():
    db = SessionLocal()
    bad = {r.scam_type for r in db.query(Report).all()
           if r.scam_type and r.scam_type not in CANONICAL_SCAM_TYPES}
    db.close()
    assert not bad, f"non-canonical scam_type values in DB: {sorted(bad)}"
```

An unenforced schema is not a schema.

---

## P4 — Temporal decay must not treat ingestion date as event date (audit M2)

70 of 188 records share the bulk-ingestion timestamp, so 37% of the corpus is scored as
maximally fresh.

In `district_engine.py` (and delete the duplicate logic in `scoring.py`):

```diff
-    dt = r.published_at or r.created_at
-    days = (now - dt).days
-    weight = exp(-LAMBDA * days) * source_weight
+    if r.has_publish_date and r.published_at:
+        days = max(0, (now - r.published_at).days)
+        weight = exp(-LAMBDA * days) * source_weight
+    else:
+        # Undated: ingestion time is not event time. Assign the decay value at
+        # the corpus median age rather than treating the record as fresh, and
+        # count it separately so coverage can be reported.
+        weight = UNDATED_DECAY * source_weight
+        undated_count += 1
```

Expose `undated_fraction` in `methodology_report()`. **If it exceeds ~0.30, temporal decay
cannot be claimed as a validated mechanism** — say so in the limitations section.

Also add `published_at` and `has_publish_date` to the export schema in
`export_clean_dataset.py`; their absence is currently concealing this problem.

---

## P5 — One scoring implementation, not four (audit B4)

`frontend/src/SafeTravelLK_Page1.jsx` re-implements district scoring in JavaScript
(`wilsonLower`, `BAYESIAN_ALPHA`, `GLOBAL_PRIOR`, quantile tiering). The map can therefore
disagree with the API the thesis documents.

1. Delete the client-side scoring block entirely.
2. Consume `risk_score_0_1`, `risk_tier`, `confidence`, `exposure_status` from
   `/api/v1/districts/risk-map`. The frontend performs **no arithmetic on risk**.
3. Move `app/core/scoring.py` and `app/core/clustering.py` to `legacy/` with a README
   stating they are superseded by `district_engine.py`.
4. Delete the duplicate `SafeTravelLK_Analytics.jsx` at the repository root (audit m7); keep
   only `frontend/src/`.

Add a regression test so the two can never drift again:

```python
# backend/tests/test_single_source_of_truth.py
def test_no_client_side_risk_arithmetic():
    src = open("../frontend/src/SafeTravelLK_Page1.jsx", encoding="utf-8").read()
    for banned in ("wilsonLower", "BAYESIAN_ALPHA", "GLOBAL_PRIOR", "computeQuantiles"):
        assert banned not in src, (
            f"{banned} found in frontend — district risk must come from the API only"
        )
```

---

## P6 — Fail loudly in research mode (audit m4)

`session.py` silently falls back from PostgreSQL to SQLite on any exception, so an
evaluation run can read a different database than intended without saying so.

```diff
     except Exception as e:
+        if os.getenv("RESEARCH_MODE", "").lower() == "true":
+            raise RuntimeError(
+                f"RESEARCH_MODE: refusing to fall back to SQLite. "
+                f"PostgreSQL connection failed: {e}"
+            ) from e
         print(f"[DB] PostgreSQL unavailable ({e.__class__.__name__}): {e}")
```

---

## P7 — Deduplicate on content, not URL + title prefix (audit m3)

4 duplicate titles and 4 duplicate contents survive the current dedup.

```python
import hashlib, re

def content_fingerprint(title: str, content: str) -> str:
    """Whitespace- and punctuation-insensitive fingerprint of the first 500 chars."""
    norm = re.sub(r"[^a-z0-9 ]", "", f"{title} {content}".lower())
    norm = re.sub(r"\s+", " ", norm).strip()[:500]
    return hashlib.sha256(norm.encode()).hexdigest()
```

Add a unique index on the fingerprint column and backfill.

---

## P8 — Housekeeping before submission

```bash
# Confirm no API key ever reached git history (audit m5)
git log -S "AIza" --all --oneline        # rotate any key that appears
git log -S "GEMINI_API_KEY" --all --oneline

# Absolute Windows paths in committed artefacts (audit m6)
grep -rn "E:\\\\research" --include="*.py" --include="*.json" --include="*.md" .

# Duplicate analytics file (audit m7)
git rm SafeTravelLK_Analytics.jsx        # keep frontend/src/ copy only
```

Also delete the unused `HARD_EXCLUSIONS` in `nlp_pipeline.py` (audit m2) — it is dead code
that diverges from the live list in `strict_filter.py`, and it is the copy containing
`"british"`, `"london"` and `"united kingdom"`, which would exclude a large share of the
tourist incidents you are studying if it were ever wired in.

---

## Deployment order

| Order | Patch | Why first |
|---|---|---|
| 1 | P2 | Nothing measured before the corpus is frozen is reproducible |
| 2 | P1, P6, P8 | Cheap; unblocks the audit scripts |
| 3 | P3, P7 | Data quality — must precede annotation, or you annotate dirty records |
| 4 | P5 | Single source of truth — must precede any reported figure |
| 5 | P4 | Changes scores; re-run the sensitivity sweep afterwards |
| 6 | `strict_filter_v2.py` | Changes corpus composition; re-freeze the snapshot afterwards |
