# District Risk Scoring — Methodology & Design Rationale
IT22629180 — SafeTravel LK

This document exists so that every number on the district choropleth can be
traced back to a formula, a data source, and a stated limitation. It is meant
to be handed to a review panel alongside the code.

## 1. What was wrong with the previous map (image: circle-marker heatmap)

The old pipeline (`app/core/scoring.py` + `app/core/clustering.py`) grouped
reports into **0.02° grid cells** (~2 km) and scored each cell independently.
That is the root cause of "everything is red":

- Most grid cells only ever accumulated **1–5 reports**. With N that small,
  `scam_ratio = scam_reports / total_reports` swings from 0 to 1 on a single
  report. One angry TripAdvisor review in an otherwise-unreported spot is
  statistically indistinguishable, in that formula, from ten corroborating
  Tier-0 government advisories.
- No exposure/visitor-volume denominator was actually implemented in code.
  The design document described an NRSI formula using SLTDA footfall data,
  but `scoring.py`/`clustering.py` never used it — every score was raw
  incident density, so the busiest (most-visited, most-reviewed) tourist
  spots always looked the most "dangerous," which is the exact "denominator
  problem" the project set out to solve, just not yet wired into the code
  that actually renders the map.
- Thresholds were fixed absolutes (`score >= 0.70 == High`). A fixed cutoff
  cannot adapt if the underlying data volume or classifier calibration shifts.

## 2. What changed

A new module, `app/core/district_engine.py`, aggregates at the **district**
level (22 polygons — see §6 on why 22, not 25) instead of an arbitrary grid.
District-level aggregation is the standard unit in tourism-safety and crime
mapping literature specifically because it is the smallest unit at which
report counts are typically large enough (tens to low hundreds) for a ratio
to be statistically meaningful, and it is also the unit SLTDA publishes
visitor-footfall data for.

## 3. The scoring formula

For a district with reports `r_1..r_n`:

```
weight(r_i)      = decay(r_i) × source_weight(r_i)
decay(r_i)       = exp(-λ × days_since_report),  λ = ln(2)/180   (180-day half-life)
source_weight    = Tier 0=1.00, Tier 1=0.80, Tier 2a=0.50, Tier 2b=0.35, Tier 3=0.25

weighted_evidence   = Σ weight(r_i)                          over ALL reports (denominator)
weighted_incidents  = Σ weight(r_i) × (risk_level_i / 3)      over SCAM-FLAGGED reports only

scam_ratio  = weighted_incidents / weighted_evidence           (Bayesian dilution: safe
                                                                 reports enlarge the
                                                                 denominator without
                                                                 touching the numerator)
severity    = weighted_incidents / scam_report_count

base_risk_score = 0.70 × severity + 0.30 × scam_ratio           (bounded ~[0,1])
```

This keeps the same decay/source-weight conventions as the original
point-level `scoring.py`, so the two layers stay comparable, but the
denominator (`weighted_evidence`) is now computed over dozens–hundreds of
reports per district instead of 1–5 per grid cell.

## 4. Exposure normalisation (the actual "Denominator Problem" fix)

Where SLTDA has published a telecom-inbound-presence footfall figure for a
district (`app/ml/exposure_baseline.py`):

```
incident_rate_per_100k = (weighted_incidents / footfall) × 100,000
```

This is reported alongside `base_risk_score`, not silently substituted for
it, because SLTDA has only published footfall for **8 of the 22** district
polygons used here (Colombo, Galle, Gampaha, Kandy, Matale, Kalutara, Matara,
Badulla). Fabricating a number for the other 14 would be worse than
disclosing the gap. Every district's API response carries an explicit
`exposure_status: "official" | "unavailable"` field, and the UI visibly
flags `unavailable` districts as "density-only, not exposure-normalised."

**This is a real, disclosed limitation of the current data — not a bug.**
When the panel asks "how do you know District X isn't just under-reported,"
the honest answer is: for districts without SLTDA footfall, the model does
not claim to know that, and says so.

## 5. Confidence gating and quantile tiering (fixes "everything red")

Two independent safeguards, both necessary:

**(a) Confidence tiers, based on absolute report count** (not proportion):
- `< 5` reports → `insufficient_data`. No risk tier/colour is assigned at all.
- `5–14` reports → `preliminary`. Scored, but visually distinct from…
- `≥ 15` reports → `established`.

These cutoffs are a design choice, not derived from the data — they encode
the minimum-N convention used in small-area crime-rate estimation (a ratio
from n<5 is not treated as a rate in most public-health/crime-mapping
practice; the exact cutoff is a defensible, statable parameter, not a
"magic number" hidden in the code).

**(b) Quantile (relative) tiering, computed fresh on every request:**
Only among districts that clear the confidence floor, the current
`base_risk_score` distribution is split at its 25th/50th/75th percentiles
into Low / Moderate / High / Severe. This means "Severe" always means "top
quartile of today's evidence," not "happened to clear 0.70 in 2024." If the
classifier's calibration drifts, or 10x more reports come in next month, the
map re-calibrates itself instead of drifting toward all-red or all-green.

## 6. Boundary data provenance

`app/data/sri_lanka_districts.geojson` uses Sri Lanka's **22 electoral
district** boundaries (Ampara, Anuradhapura, Badulla, Batticaloa, Colombo,
Galle, Gampaha, Hambantota, Jaffna, Kalutara, Kandy, Kegalle, Kurunegala,
Matale, Matara, Monaragala, Nuwara Eliya, Polonnaruwa, Puttalam, Ratnapura,
Trincomalee, and a merged "Vanni" polygon covering Mannar, Vavuniya and
Mullaitivu), sourced from `github.com/thejeshgn/srilanka` (derived from GADM
2.7 `LKA_adm1`, CC-BY), geometry-simplified (Douglas–Peucker, ~400 m
tolerance) for web performance.

**Why 22 and not the 25 administrative districts:** the electoral map merges
Mannar, Vavuniya and Mullaitivu into a single "Vanni" polygon. This is
disclosed in each feature's `constituent_admin_districts` property so the
gap is visible in the data itself, not just in this document. If a true
25-polygon administrative (DS-division-derived) boundary file becomes
available, only `app/data/sri_lanka_districts.geojson` needs to be replaced
— `district_engine.py` is written generically against
`(district_name, constituent_admin_districts)` pairs and does not hardcode 22
anywhere.

## 7. What a panel member can ask the running system directly

`GET /api/v1/districts/methodology` returns every constant above
(decay half-life, confidence thresholds, weighting scheme, and — critically
— the live SLTDA coverage ratio) as JSON, so the methodology is a live,
inspectable artifact rather than only a static claim in this document.

## 8. Known limitations to state proactively

1. Exposure normalisation covers 8/22 districts today; the rest are
   density-only and are labelled as such everywhere they appear.
2. `risk_level` (1–3) is produced upstream by the NLP classifier
   (`app/ml/nlp_pipeline.py`) and is not independently validated against a
   ground-truth labelled set in this build; severity is only as good as that
   classifier.
3. Electoral-district boundaries are a proxy for administrative districts
   (see §6). This is disclosed, not hidden.
4. Quantile tiering is relative, not absolute: a "Severe" tier today does not
   guarantee the same absolute risk score as a "Severe" tier six months from
   now once more data accumulates. This is a deliberate trade-off (relative
   ranking beats a stale absolute cutoff) and should be stated as such in the
   thesis, with the live methodology endpoint as evidence.
