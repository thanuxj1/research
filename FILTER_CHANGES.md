# Relevance Filter Fixes — SafeTravel LK
**IT22629180**

---

## Problem Summary

The pipeline was collecting irrelevant data — news articles, political stories, crime reports, and general web content that had nothing to do with tourists' negative experiences in Sri Lanka. The root causes:

### Root Cause 1 — Weak single-keyword matching in `strict_filter.py`
The old filter accepted any text containing ONE negative word (`"bad"`, `"problem"`, `"issue"`, `"sad"`) AND ONE tourist term. This allowed:
- General Sri Lanka news articles mentioning "bad weather" and "tourist season"
- Political stories mentioning "problem" + "travelers"
- Crime reports about drug busts mentioning "danger"

### Root Cause 2 — No scoring / confidence threshold
All items that passed were treated equally, regardless of whether they had 1 weak match or 10 strong matches. There was no minimum confidence gate.

### Root Cause 3 — Google Maps collected off-country places
The Places API sometimes returns places outside Sri Lanka for ambiguous queries. Without coordinate validation, reviews from other countries were accepted if the text happened to match keywords.

---

## Fixes Applied

### Fix 1 — `data_pipeline/strict_filter.py` — Scored relevance engine

**Old approach:** Boolean — if ANY negative word + ANY tourist word → pass.

**New approach:** Weighted scoring across three tiers of signals:

| Signal Tier | Examples | Score per match |
|---|---|---|
| Strong tourist context | "tourist", "traveller", "backpacker", "solo trip", "vacation" | +2.0 |
| Tourism infrastructure | "hostel", "tuk tuk", "tour guide", "safari", "day trip" | +1.0 |
| High-weight negative | "scam", "ripped off", "pickpocket", "assault", "food poisoning" | +3.0 |
| Medium-weight negative | "overpriced", "dirty", "refund", "terrible", "hospital" | +1.0 |
| Weak/ambiguous negative | "bad", "problem", "issue", "sad", "complain" | +0.5 (only if already has negative score) |

**Minimum thresholds to pass:**
- Must have tourist score > 0 (at least one tourist signal)
- Must have negative score ≥ 3.0 (at least one high-weight negative, or 3 medium ones)
- Must have total combined score ≥ 5.0

**Result:** A generic article saying "bad road near tourist area" scores ~2.5 (tourist+1 + weak neg+0.5) → REJECTED. A post saying "scammed by tuk tuk driver in Colombo" scores ~8.0 (tourist+2 + scam+3 + location) → ACCEPTED.

The new `score_relevance()` function also returns a full breakdown of matched signals, enabling audit logging.

### Fix 2 — `data_pipeline/collectors/google_maps.py` — Bounding box validation

Added `_coords_in_sri_lanka(lat, lng)` that validates every collected place's coordinates against Sri Lanka's geographic bounding box (Lat: 5.7–10.0, Lon: 79.4–82.1) before processing its reviews. Places outside this box are logged and skipped.

### Fix 3 — `data_pipeline/main_pipeline.py` — Rejection reason logging

The pipeline now logs a full breakdown of WHY items were rejected:
```
FILTER REJECTION BREAKDOWN:
  no_tourist_context                             1,203
  insufficient_negative_signals                    847
  hard_exclusion                                   421
  no_sri_lanka_geography                           312
  low_total_relevance_score                        108
```
This helps you diagnose data quality issues after each pipeline run.

### Fix 4 — `backend/export_clean_dataset.py` — New clean dataset exporter

A new script that:
1. Reads all records from the database
2. Re-runs the improved filter on every record (retroactively cleaning existing data)
3. Exports a clean CSV with all source URLs

**Usage:**
```bash
# Basic export
python export_clean_dataset.py

# Export + save rejection audit log
python export_clean_dataset.py --audit

# Custom output path
python export_clean_dataset.py --out /path/to/my_dataset.csv
```

**Output CSV columns:**
- `id` — Record ID
- `source` — Data source (youtube, google_maps, adaderana, etc.)
- `source_url` — Original URL (for traceability/verification)
- `title` — Article/review title
- `content` — Full text
- `location_name` — Named location in Sri Lanka
- `latitude`, `longitude` — Coordinates
- `scam_type` — Classified scam category
- `risk_level` — 1 (low) to 3 (high)
- `sentiment_score` — –1.0 to +1.0
- `is_scam` — Binary flag
- `relevance_score` — Combined filter score (higher = more relevant)
- `tourist_score` — Tourist context component
- `negative_score` — Negative experience component
- `matched_signals` — All keyword signals that fired (pipe-separated)
- `created_at` — Timestamp

---

## Files Changed

| File | Change |
|---|---|
| `data_pipeline/strict_filter.py` | Rewritten — scored relevance engine replacing boolean filter |
| `data_pipeline/main_pipeline.py` | Updated to use `score_relevance()` and log rejection reasons |
| `data_pipeline/collectors/google_maps.py` | Added Sri Lanka bounding box check before accepting reviews |
| `backend/export_clean_dataset.py` | **New file** — clean dataset exporter with source URLs |

