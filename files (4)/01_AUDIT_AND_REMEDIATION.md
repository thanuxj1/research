# SafeTravel LK — Research-Grade Audit & Remediation Plan
**Component:** Dynamic Safety Heatmap & Scam Analytics Engine
**Student:** IT22629180 | **Project:** R26-IT-022 | **Audit date:** 17 Aug 2026

This audit was performed against the actual code and the actual exported corpus
(`dataset_exports/safety_incidents_dataset.csv`, n=188), not against the documentation.
Where the documentation and the code disagree, the code is treated as ground truth.

**Severity key:** 🔴 Blocker (will fail a panel / invalidates a claim) · 🟠 Major (weakens a
contribution) · 🟡 Minor (polish / consistency).

---

## 0. Executive summary

The engineering is well ahead of the research. You have a working ingestion → NLP →
aggregation → visualisation stack, and several of the honest-disclosure moves already in
the repo (the methodology endpoint, the circular-validation warning banner, the gated demo
fixtures, the ablation script) are exactly what a panel wants to see.

What is missing is the part that makes it *research* rather than *a system*: there is no
research question stated in falsifiable form, no ground truth, no baseline, no measured
result, and the single claim you nominate as your "most significant contribution"
(demographic-adaptive risk) currently has **zero supporting data in the corpus**.

Four things must change before this is defensible:

| # | Blocker | One-line fix |
|---|---|---|
| B1 | Flagship novelty (demographic adaptation) has no data and no method | Make demographic-signal extraction a *research task* with its own labelled set and metric (§2.1) |
| B2 | No ground truth → no precision/recall → no result | Execute the gold-set protocol; `evaluate_gold_set.py` is now written for you (§2.2) |
| B3 | Documentation claims 16,000+ records; corpus is 188 | Restate every count from the frozen corpus snapshot; delete the 16k claim (§2.3) |
| B4 | Four divergent scoring implementations | Backend `district_engine` becomes single source of truth; frontend renders only (§2.4) |

Everything else is a Major or Minor and is listed with a specific remedy below.

---

## 1. What is already right (state this in the defence — do not hide it)

These are genuine strengths and you should lead with them, because they are unusual at
undergraduate level:

1. **`docs/DISTRICT_RISK_METHODOLOGY.md`** traces every constant to a formula and a stated
   limitation. Keep this; it is your strongest artefact.
2. **`GET /api/v1/districts/methodology`** exposes the constants as live JSON. A panel can
   interrogate the running system. Very few student projects can do this.
3. **`show_model_accuracy.py` carries an explicit circular-validation warning.** Declaring
   that your own accuracy number is invalid is a mark of research maturity, not weakness.
4. **`demoFixtures.js` is gated behind `?demo=1`** with a visible banner. Fabricated data
   cannot silently reach the screen.
5. **`insufficient_data` is a distinct tier from `low`.** Absence of evidence is not
   rendered as evidence of safety — this is the correct call and is defensible on ethics
   grounds as well as statistical ones.
6. **`scam_taxonomy.py` exists** and documents the four vocabularies it was written to
   unify. (It is not yet applied at write time — see M7.)

---

## 2. Blockers

### B1 🔴 The flagship novelty has no empirical basis

**Claim in TAF:** *"The most significant contribution is the personalization of safety…
adjusting the heatmap based on the user's input (Solo Female vs. Group)."*

**Reality in the corpus:**

```
demographic_target value counts (n=188)
  Tourists                     148
  Tourists / Travel Vloggers    40
```

Two values, neither of which is a demographic. Zero records identify a solo female
traveller, a family, a couple, or a senior. The multipliers that drive the entire feature
are hand-written constants in `app/ml/clustering_service.py`:

```python
DEMOGRAPHIC_WEIGHTS = {
    "Solo Female": {"harassment": 1.6, "gem_scam": 1.1, ...},
```

Your own code already admits this — `district_engine.methodology_report()` returns:

> `"demographic_multipliers_caveat": "Risk multipliers (1.2× Solo Female, etc.) are illustrative. No empirical derivation. Sensitivity analysis pending."`

A panel that reads that line and then reads "most significant contribution" in the TAF
will conclude the contribution is asserted, not demonstrated. **This is the single most
likely reason for a topic rejection or a major-revision verdict.**

**Remediation — turn the weakness into the research contribution.** The gap *is* the
research problem. Reframe the component as: *victim-demographic signals are latent in
free-text incident reports and have never been extracted at scale for tourism safety.*
That gives you a real, novel, evaluable task:

1. **Define the extraction task.** From incident text, predict `victim_profile ∈ {solo_female,
   solo_male, couple, family, group, unknown}` using explicit textual evidence ("a British
   woman travelling alone", "my husband and I", "we took our two children").
2. **Build the labelled set.** 400 records, hand-annotated, `unknown` allowed and expected
   to be the majority class. Report the `unknown` rate — it is a finding, not a failure.
3. **Measure extraction.** Macro-F1 per class + Cohen's κ between two annotators. Report
   per-class support; do not report a single pooled accuracy.
4. **Derive, do not assert, the multipliers.** For each (demographic × scam_type) cell,
   compute the risk ratio *with a Wilson or Clopper–Pearson interval*. Cells whose
   interval spans 1.0 get a multiplier of **1.0** and are reported as *not significant at
   this corpus size*. This is the honest version and it is far more defensible than 1.6.
5. **Sensitivity analysis.** Perturb every multiplier ±25% and report the Kendall τ of the
   resulting district ranking against the unperturbed ranking. If τ > 0.9, state plainly
   that the multipliers barely matter at this N — that is a legitimate, publishable
   negative result. `code/sensitivity_analysis.py` implements this.

**Fallback if annotation time runs out:** demote the claim from "adaptive risk scoring" to
"demographic-conditional *surfacing*" — the multipliers reorder which incidents are shown
first, but do not alter the district risk score. That is a UI personalisation claim, is
fully honest, and cannot be attacked on statistical grounds.

---

### B2 🔴 No ground truth, therefore no measured result

`show_model_accuracy.py` cross-validates against labels produced by the same keyword rules
that do the classification. The script says so itself. Any number it prints is a measure of
rule self-consistency, not of accuracy.

`scripts/gold_set_instructions.md` specifies the correct protocol, but Step 4 references
`evaluate_gold_set.py`, which **does not exist in the repository**.

**Remediation:** `code/evaluate_gold_set.py` is delivered with this audit. It computes,
per corpus and per class: precision, recall, F1, support, macro/weighted averages,
bootstrap 95% CIs, a confusion matrix, geocoding accuracy, `body_mention` exclusion effect,
and Cohen's κ from a double-annotated subset. It refuses to pool corpora into one figure.

**Sample-size justification (put this in the thesis, panels ask for it):** for a binary
scam/not-scam decision, a 95% Wilson interval on a proportion near 0.85 with n=388 has a
half-width of ≈ ±3.6 percentage points. That is adequate for a claim of the form
"precision is above 0.75". It is *not* adequate for per-scam-type F1 on the rare classes —
`accommodation_scam` has n=1 in the current corpus. **State explicitly that per-class
metrics are only reported for classes with support ≥ 20**, and list the excluded classes.

---

### B3 🔴 Documentation and reality disagree by two orders of magnitude

`docs/FULL_SYSTEM_DOCUMENTATION.md` §1 states the system *"aggregates 16,000+
cross-referenced incident reports."* The exported corpus is **188 records**. The 16,156
figure is the raw TripAdvisor review CSV — reviews of hotels and attractions, the
overwhelming majority of which are not incidents. Presenting review count as incident
count will be read as inflation.

Further inconsistencies found:

| Location | Claim | Actual |
|---|---|---|
| FULL_SYSTEM_DOC §1 | 16,000+ incident reports | 188 |
| FULL_SYSTEM_DOC §7.3 | risk-map returns "25 districts" | GeoJSON has 22 polygons |
| FULL_SYSTEM_DOC §7.3 sample | `"report_count": 847` for Colombo | 74 |
| FULL_SYSTEM_DOC §9.2 | "SVG bubble map of all 25 districts" | 12 districts have any data |
| FULL_SYSTEM_DOC §13 | Tier-0 government advisories ingested | **0 government records in corpus** |
| FULL_SYSTEM_DOC §2.2 | 11 SL news outlets scraped | 5 outlets present, 14 records total |

**Remediation:** freeze a corpus snapshot (§3, M1), regenerate every count in the
documentation from that snapshot, and add a header line to the doc: *"All counts in this
document are generated from corpus snapshot `<hash>` dated `<date>`."* Delete the 16k
claim entirely and describe the review CSV as what it is: *a 16,156-review corpus from
which N safety-relevant records were extracted at a yield rate of X%* — the yield rate is
itself a reportable result.

---

### B4 🔴 Four different scoring formulas coexist

| Implementation | Formula | Used by |
|---|---|---|
| `app/core/scoring.py` | `0.75·avg_severity + 0.25·scam_ratio`, then × avg decay | legacy grid clustering |
| `app/core/district_engine.py` | `0.70·severity + 0.30·scam_ratio`, Wilson + shrinkage + quantile tiers | `/districts/risk-map` |
| `app/core/safety_intelligence.py` | 5-component composite (0.30/0.25/0.20/0.15/0.10) | `/safety/assess` |
| `frontend/src/SafeTravelLK_Page1.jsx` | re-implements district scoring **in JavaScript** | the map the user actually sees |

The same district can therefore carry two different risk scores depending on which
endpoint you ask, and the map may disagree with the API that the thesis describes. This is
a reproducibility failure: a reviewer re-running your API will not reproduce your figures.

**Remediation:**
1. `district_engine.py` is the single source of truth for district scores. Delete the JS
   re-implementation; the frontend consumes `risk_score_0_1` and `risk_tier` from the API
   and performs **no arithmetic**.
2. `safety_intelligence.py` (IDW point scoring) is retained but explicitly scoped as a
   *different question* — "risk at this coordinate", not "risk in this district" — and the
   thesis must say so in one sentence. Two engines answering two questions is fine; two
   engines answering the same question is not.
3. `scoring.py` + `clustering.py` (grid path) are dead relative to the district engine.
   Either delete them or move them to `legacy/` with a README stating they are superseded.
   Leaving superseded code in the main tree invites the panel to ask which one produced
   your numbers.

---

## 3. Major findings

### M1 🟠 The corpus is not frozen — results are not reproducible

`app/main.py` launches a continuous scraper subprocess **on every API startup** and
schedules a daily 02:00 deep collection. The database therefore mutates continuously.
Quantile tiers are recomputed per request against the current distribution. Consequently
the same query returns different answers on different days, and no figure in your thesis
can be reproduced.

**Remediation:**
- Add `RESEARCH_MODE=true` to `.env`. When set, `start_automated_systems()` skips both the
  scheduler and the continuous collector. Run all evaluation in research mode.
- Export a versioned, hashed snapshot before every evaluation run:
  `corpus_v1_2026-08-17_sha256-<12 chars>.jsonl`. Cite the hash in the thesis.
- Report all headline results against the frozen snapshot; use the live pipeline only to
  demonstrate that continuous ingestion works.

### M2 🟠 Temporal decay is applied to ingestion dates for most of the corpus

`created_at` distribution shows **70 of 188 records (37%) share the single timestamp
`2026-08-06`** — the bulk-ingestion date. `scoring.py` uses `created_at` unconditionally.
`district_engine` prefers `published_at` but falls back to `created_at`, and the exported
dataset carries **no `published_at` column at all**, indicating near-zero real coverage.

Effect: a 2019 news article ingested last week receives a temporal weight of ≈1.0, the same
as an incident from yesterday. The 180-day half-life — one of your headline mechanisms — is
inoperative on more than a third of the data, and silently so.

**Remediation:**
- Report `has_publish_date` coverage as a headline data-quality statistic. If it is under
  ~70%, temporal decay **must not** be claimed as a validated mechanism.
- Records without a true publication date should be excluded from decay-weighted scoring
  (assign weight from a separate "undated" bucket) rather than defaulted to "fresh".
- Add `published_at` to the export schema. Its absence is currently hiding the problem.

### M3 🟠 The relevance filter encodes systematic selection bias

`data_pipeline/strict_filter.py` performs **substring** matching over `HARD_EXCLUSIONS`
with no word boundaries and no carve-outs. Three distinct failure modes:

**(a) Nationality terms exclude the victims you are studying.** The list contains
`"france"`, `"italy"`, `"europe"`, `"greece"`, `"spain"`, `"dubai"`, `"oman"`. A headline
*"French tourist assaulted in Galle"* is hard-excluded. The exclusion was written to filter
incidents occurring *in* those countries; it also filters incidents whose *victim* is from
them — which is the exact population under study. Running the current filter over the
already-stored corpus rejects 6 records that are in the database, on `oman`, `bangkok`,
`dubai`, `italy`, `france` and `ganja` — confirming the filter and the corpus are already
inconsistent with each other.

**(b) Advisory vocabulary is excluded, which is why Tier-0 coverage is zero.** The list
contains `"protest"`, `"curfew"`, `"riot"`, `"minister"`, `"cabinet"`, `"high commission"`.
Government travel advisories (UK FCDO, US State Dept, Smartraveller) are built almost
entirely from that vocabulary. The corpus contains **zero Tier-0 records** despite Tier-0
sitting at weight 1.00 at the top of your credibility hierarchy. Your highest-credibility
tier is empty and the filter is the reason.

**(c) Substring matching over-fires.** `"minister"` matches inside `"administer"`;
`"employment"` inside `"unemployment"`; `"protest"` inside `"protested"`, `"protesters"`.
There is a word-boundary guard in `_check_exclusions()` but it only applies to patterns of
length ≤ 3, so it never fires for any of these.

**Remediation:** `code/strict_filter_v2.py` is delivered. It (i) matches on word
boundaries via compiled regex, (ii) separates `GEO_EXCLUSIONS` (incident location) from
nationality mentions and requires a Sri Lankan geo-anchor before excluding, (iii) adds an
`ADVISORY_OVERRIDE` so official-advisory sources bypass political-vocabulary exclusions,
and (iv) returns a structured `rejection_reason` for every rejected item so that filter
error rates become *measurable*.

**And measure it.** Sample 200 rejected items, hand-label them for true relevance, and
report the filter's false-negative rate. A filter you cannot characterise is an
uncontrolled variable in every downstream number.

### M4 🟠 Bayesian shrinkage as configured is cosmetic

`α = 0.05`, `prior = 0.30`:

```
N=3,  raw=0.80  →  shrunk = (3×0.80 + 0.05×0.30)/(3+0.05) = 0.792
N=1,  raw=1.00  →  shrunk = (1×1.00 + 0.05×0.30)/(1+0.05) = 0.967
```

Your own documentation reports 0.766 for the N=3 case; the formula gives 0.792. Either way,
α = 0.05 means the prior carries the weight of **one twentieth of one observation**. With
N=1 the score is still 0.967. The mechanism is named in the thesis but does essentially
nothing.

**Remediation:** α is a *pseudo-count* and should be on the scale of the evidence you want
it to overcome — α ∈ [5, 20] for a corpus with tens of reports per district. Choose α by
stating the design intent explicitly ("a district needs ~10 real reports before its own
data dominates the prior"), then run the sensitivity script over α ∈ {0.05, 1, 5, 10, 20}
and report how the district ranking changes. Justify the final value from that table, not
from a round number.

### M5 🟠 Two composite components measure data volume, not risk

In `safety_intelligence.py`:

- **Scam diversity penalty (20% of the score)** = `min(unique_scam_types / 5, 1)`. A
  location with more *kinds* of report scores higher. Report variety is driven by report
  volume, which is driven by tourist volume — this reintroduces the exact denominator
  problem your district engine was built to solve, at 20% weight.
- **Credibility factor (15%)** = `min(tier1_confirmed_scams / 3, 1)`. Counts Tier-1
  confirmations. Media attention is a function of prominence, not of danger.

Together, 35% of the point-level composite is a proxy for "how much is written about this
place".

**Remediation:** either (a) normalise both by total reports at that location (diversity
becomes *Shannon entropy* of the scam-type distribution, which is volume-invariant), or
(b) drop them and state the reduction in the thesis. Run the ablation script both ways and
report the rank correlation — if removing 35% of the formula changes nothing, that is a
finding about the formula.

### M6 🟠 "Micro-location scam detection" is not supported by the data

TAF novelty claim: *"this system uses clustering to identify specific 'micro-locations' —
such as a specific fraudulent shop or a street corner known for touts."*

Actual geocoding is a dictionary of ~25 named destinations, longest-match against title and
first 500 characters. Every incident in Kandy receives *the same* coordinate. DBSCAN then
runs at `eps = 0.5 km, min_samples = 3` over points that are snapped to ~25 distinct
locations. The resulting "clusters" are an artefact of the geocoding dictionary, not
spatial structure in the phenomenon. There is no street-level or venue-level coordinate
anywhere in the corpus.

**Remediation (pick one and commit in the TAF):**
- **Honest scope reduction (recommended):** drop "micro-location" from the novelty claims
  and state the spatial resolution as *destination-level*, which is what the data supports.
  Add a sentence: *"Venue-level resolution requires venue-tagged sources (Google Places
  review anchors); this is scoped as future work."*
- **Or earn it:** ingest Google Places review data with true `place_id` anchors, giving real
  venue coordinates, and demonstrate clustering on that subset only. This is real work;
  budget for it before promising it.

Either way, do not leave the claim as written — it is the easiest thing on the form for a
panel to falsify by reading one file.

### M7 🟠 Taxonomy is defined but never enforced

`scam_taxonomy.py` defines 11 canonical keys and exists specifically to unify four
vocabularies. The exported corpus contains a **fifth**: `Safety Advisory (Non-Incident)`,
`General Safety Incident`, `Gem / Jewellery Scam` (canonical display is `Gem & Jewellery
Scam`), and raw `scam_type` still shows both `Tuk-Tuk Scam` and `Tuk Tuk Scam` as separate
values. Source keys are fragmented too: `newswire` (4) and `newswire_lk` (1) are the same
outlet counted twice, which splits their credibility weighting.

**Remediation:** call `scam_taxonomy.normalise()` at **write time** in every ingestion path
(`ingest_reviews_csv.py`, `scrape_sl_news_v3.py`, all collectors), add a source-key alias
map, then run a one-off migration over the existing DB. Add a unit test asserting that
every distinct `scam_type` in the DB is in `CANONICAL_SCAM_TYPES` — an unenforced schema is
not a schema.

### M8 🟠 Geocoding accuracy is unmeasured and Colombo attribution looks inflated

Colombo holds **74 of 188 records (39.4%)**. Colombo is the dateline, the byline city, and
the national reference point in Sri Lankan press writing; a longest-match geocoder over
article text will attribute national-scope articles to Colombo. `district_engine` already
flags this (`geocode_bias_note`, and a `body_mention` exclusion), but the effect has never
been quantified.

**Remediation:** hand-audit a random 60-record Colombo sample. Report the proportion where
the *incident* — not the article — occurred in Colombo. Report geocoding accuracy overall
and per confidence band (`title_match` / `first_200_words` / `body_mention`). If
`body_mention` accuracy is below ~0.6, exclude that band from scoring and say so. Four
records are geocoded to the literal string `"Sri Lanka"` and must be routed to a
`national` scope, not a district.

### M9 🟠 The corpus does not support district-level conclusions and the thesis must say so

Under your own confidence thresholds, the corpus yields:

- **established** (≥15 reports): Colombo (74), Kandy (21), Nuwara Eliya (20), Galle (16) — **4 districts**
- **preliminary** (5–14): Monaragala, Matale, Kegalle, Jaffna, Polonnaruwa — **5 districts**
- **insufficient** (<5): Trincomalee (3), Anuradhapura (1) — **2 districts**
- **no data at all: 13 of 25 administrative districts**

Also: `risk_level = 3` appears in only 14 records (7.4%), and severity is 70% of the
district score — so the severity component of the entire map is driven by fourteen
records.

`methodology_report()` already contains the right sentence:

> *"188 records, 4 districts at 'established' confidence. Corpus demonstrates the method;
> does not support conclusions about actual Sri Lankan district safety ordering."*

**Remediation:** promote that sentence from a JSON field to the **abstract, the results
chapter, and the slide deck**. Frame the contribution as *a method and its evaluation*, not
*a safety map of Sri Lanka*. This is both honest and strategically correct: "we built and
validated a scoring method, and demonstrated it on a pilot corpus" is a defensible
undergraduate research contribution. "We mapped Sri Lanka's tourist risk" is not, at n=188.

### M10 🟠 The LLM advisory path is unevaluated in a safety-critical context

`/advisor/chat` calls Gemini 1.5-flash with DB context injected, and falls back to
keyword rules. Nothing measures whether the advice is correct. In a safety application, a
confidently wrong answer ("that area is fine at night") is the highest-severity failure the
system can produce, and it is currently the only component with no evaluation at all.

**Remediation:** build a 50-question evaluation set with reference answers derived from the
corpus. Score each response on (i) factual grounding — every claim traceable to a retrieved
report, (ii) no fabricated incidents, (iii) appropriate hedging when evidence is thin.
Report a hallucination rate. Add a hard system-prompt constraint that the model may only
reference incidents present in the injected context, and that it must say "I don't have
data for that area" when the district is `insufficient_data`.

### M12 🟠 The relevance filter is not applied uniformly across ingestion paths

`strict_filter.py` is invoked by the news pipeline. The CSV ingestion paths
(`ingest_reviews_csv.py`, `import_all_reviews.py`, `ingest_primary_dataset.py`) and several
collectors do not call it. Corpus composition therefore depends on *which script inserted
the record*, which is an uncontrolled variable.

Evidence: running the corrected filter (`code/strict_filter_v2.py`) over the 188 stored
records accepts only **61**. The remaining 127 reject as follows:

```
insufficient_negative_signals   59
no_tourist_context              42
no_geo_anchor                   16
below_total_threshold            9
hard_exclusion                   1
```

Two distinct issues are visible here, and both need stating:

1. **Uniformity.** A single filter must gate every write path, or the corpus is a union of
   differently-filtered subsets and no corpus-level statistic is well-defined.
2. **The filter is incident-tuned but the corpus is 43% advisories.** 81 of 188 records are
   `Safety Advisory (Non-Incident)`, which by construction carry no incident narrative and
   fail a negative-signal floor designed for incident reports. The filter needs an explicit
   **record-class branch** — incident reports and advisories are different objects with
   different acceptance criteria. `strict_filter_v2` implements this for advisory *sources*;
   extend it to advisory *content* before deploying.

**Remediation:** route every write through one filter function; add the record-class branch;
re-run over the existing DB and report how many stored records the filter would not now
accept. That delta is a data-quality result, and reporting it is far stronger than
discovering it in the viva.

### M11 🟠 Ethics section understates the actual risk profile

TAF §7 states *"No sensitive personal information will be collected"* and *"does not
involve medical, biometric, or psychological experimentation."* Both are true and both miss
the real exposure:

1. **Defamation.** The system aggregates unverified user reports and renders geographic
   areas — potentially identifiable businesses — as fraudulent. Sri Lankan law provides
   civil remedy for injurious falsehood. A single named guesthouse marked "scam" from two
   anonymous reviews is a genuine legal exposure for you and for SLIIT.
2. **Economic harm to communities.** A "Severe" tier on a district reduces visitor income
   for every operator in it, including the honest majority. Quantile tiering *guarantees*
   that 25% of scored districts are labelled Severe regardless of absolute risk — a
   district can be tiered Severe while being objectively safe, purely because it ranks in
   the top quartile of a 9-district scored set.
3. **Special-category data.** Harassment reports cross-referenced with gender-based
   demographic profiles is special-category personal data under most modern data-protection
   regimes, including Sri Lanka's PDPA (No. 9 of 2022).
4. **Platform terms.** Scraping TripAdvisor, Reddit and YouTube for redistribution has ToS
   implications that a research-ethics form should address rather than omit.

**Remediation:** add to the TAF and to the thesis an ethics subsection covering: (a) a
corroboration threshold — no location is tiered above `moderate` on fewer than *k*
independent sources, *k* stated; (b) no naming of individual businesses in any user-facing
output; (c) a stated right-of-reply / takedown channel; (d) PDPA lawful-basis statement for
the demographic fields; (e) explicit disclosure that quantile tiering is *relative*, shown
in the UI next to every tier label, so a "Severe" badge cannot be read as an absolute
safety verdict; (f) ToS position on each scraped source.

---

## 4. Minor findings

| ID | Finding | Fix |
|---|---|---|
| m1 🟡 | `scripts/ablation_study.py` imports `app.db.database`; the module is `app.db.session`. The script cannot run as written. | Change the import. Also swap `location_name` for the district resolved by `district_engine` — `location_name` holds city names, so the ablation currently aggregates at a different unit than the map. |
| m2 🟡 | `nlp_pipeline.HARD_EXCLUSIONS` is defined and never imported anywhere; `strict_filter.py` has its own divergent copy (which includes `"british"`, `"london"`, `"united kingdom"` — see M3a). | Delete the dead copy; import the single list from one module. |
| m3 🟡 | 4 duplicate titles and 4 duplicate contents remain post-dedup. | Dedup on normalised content hash, not URL + 60-char title prefix. |
| m4 🟡 | `session.py` silently falls back from PostgreSQL to SQLite on *any* exception. An evaluation run can silently read a different database than intended. | In `RESEARCH_MODE`, fail loudly instead of falling back. |
| m5 🟡 | `.env.example` present, but confirm no real `GEMINI_API_KEY` / `GOOGLE_MAPS_API_KEY` was ever committed to git history before submission. | `git log -S "AIza" --all`; rotate any key that appears. |
| m6 🟡 | Absolute Windows paths (`E:\research\...`) are baked into `dataset_stats.json` and the docs. | Make paths relative before submission; they signal a single-machine, non-portable build. |
| m7 🟡 | `SafeTravelLK_Analytics.jsx` exists in two places (repo root and `frontend/src/`) with different sizes (35,396 vs 33,964 bytes). | Delete the root copy; a reviewer cannot tell which one runs. |
| m8 🟡 | TAF says clustering uses "K-Means **or** DBSCAN". | Commit to one, in the form, with a one-line justification (DBSCAN — no *k* to pre-specify, handles noise, and hotspots are density-defined not centroid-defined). Undecided methods read as unplanned. |
| m9 🟡 | `risk_zones` table and `ClusteringService` are still wired but superseded by district aggregation. | State the relationship explicitly or move to `legacy/`. |
| m10 🟡 | TAF §5 promises "including references" and contains **no citations at all**. | See `03_TAF_IT22629180_REVISED.md` for a reference list. |

---

## 5. Ordered remediation plan

**Week 1 — Integrity (do this before anything else)**
1. Freeze corpus snapshot with hash; add `RESEARCH_MODE` flag (M1).
2. Regenerate every count in the documentation from the snapshot; delete the 16k claim (B3).
3. Delete the frontend scoring re-implementation; single source of truth (B4).
4. Fix m1, m2, m3, m7.

**Weeks 2–4 — Ground truth (the long pole; start annotation immediately)**
5. Export the gold set, annotate 388 records, second annotator on 10%, compute κ (B2).
6. Annotate `victim_profile` on the same pass — one annotation effort, two research outputs (B1).
7. Run `evaluate_gold_set.py`; these are your headline numbers.

**Week 5 — Measurement**
8. Deploy `strict_filter_v2.py`; sample 200 rejections; report filter FNR (M3).
9. Hand-audit 60 Colombo records; report geocoding accuracy per confidence band (M8).
10. Report `has_publish_date` coverage; re-scope the decay claim accordingly (M2).

**Week 6 — Parameter defence**
11. Run `sensitivity_analysis.py` across α, half-life, severity/ratio weights, and demographic multipliers (M4, M5, B1).
12. Fix ablation import and re-run; report Spearman ρ per variant.

**Week 7 — Scope and ethics**
13. Rewrite TAF novelty claims per `03_TAF_IT22629180_REVISED.md` (M6, M9, m8, m10).
14. Write the ethics subsection; implement the corroboration threshold and the
    relative-tiering disclosure in the UI (M11).
15. Build the 50-question LLM evaluation set; report hallucination rate (M10).

---

## 6. Sensitivity analysis — actual results from your corpus

`code/sensitivity_analysis.py` was run against
`dataset_exports/safety_incidents_dataset.csv` (n=188, 9 districts clearing the 5-report
floor). Kendall τ is measured against the default-parameter ranking.

| Parameter | Sweep | min τ | Verdict |
|---|---|---|---|
| Half-life $H$ | 30 → no decay | 0.833 | Consequential — justify 180 |
| Severity weight $\beta$ | 0.0 → 1.0 | 0.833 | Consequential — justify 0.70 |
| Shrinkage $\alpha$ | 0.05 → 50 | **0.333** | **Unstable** — ranking is not robust |
| Prior $\pi$ | 0.10 → 0.50 | **1.000** | **Inert** — no effect whatsoever |
| Demographic multipliers | ±25%, 200 draws | 0.722 (mean 0.935) | Consequential but weak |

Three results worth putting straight into the thesis:

**1. The prior is provably doing nothing.** τ = 1.000 across the entire range 0.10–0.50.
Changing the global prior by a factor of five does not move a single district by one rank.
This is the empirical confirmation of M4: at α = 0.05 the prior carries the weight of one
twentieth of an observation. **Either raise α or stop describing Bayesian shrinkage as a
mechanism** — currently the thesis would claim a component that measurably does nothing.

**2. α is the single most influential parameter.** At α = 20 the ranking correlation drops
to 0.556; at α = 50 it drops to 0.333 with p = 0.26 — no significant relationship to the
default ordering at all. So the parameter that is currently set low enough to be inert is
the one that would matter most if set sensibly. Sweep it, pick a value from a stated design
intent, and report the table.

**3. Jaffna ranks first, above Colombo, on five reports.** Under default parameters the top
of your district ranking is a district at `preliminary` confidence with n=5. This is the
strongest possible argument *for* the confidence gating you already built — and the
strongest possible argument against ever presenting the ranking without it. Use this
example in the defence: it shows you found the failure mode yourself and designed for it.

Run the same script after every parameter change and keep the output as an appendix.

---

## 7. The five questions the panel will ask — and your answers

**"How do you know your classifier is accurate?"**
→ *"I don't yet, and the repository says so — `show_model_accuracy.py` carries a
circular-validation warning because its labels come from the same rules being tested. The
honest measure is the 388-record gold set; here are precision, recall and F1 per corpus,
with Cohen's κ of X between annotators."*

**"Isn't Colombo just the most-reported place rather than the most dangerous?"**
→ *"That is the denominator problem and it is the reason for exposure normalisation. It is
solved for the 8 districts where SLTDA publishes footfall and explicitly unsolved for the
other 14, which are labelled `density-only` in the API and in the UI. I also hand-audited
60 Colombo records because dateline attribution inflates that district; geocoding accuracy
in that sample was X."*

**"Where does 1.6× for solo female harassment come from?"**
→ *"Originally from nothing — it was an illustrative constant, and the methodology endpoint
said so. It is now derived from the labelled subset as a risk ratio with a Wilson interval;
cells whose interval spans 1.0 are set to 1.0 and reported as not significant at this
corpus size."*

**"Can you tell me whether Galle is actually safer than Kandy?"**
→ *"No, and the system is designed not to imply that it can. 188 records give four
districts at established confidence and thirteen with no data. The contribution is the
scoring method and its evaluation, demonstrated on a pilot corpus — not a safety ranking of
Sri Lanka."*

**"What happens if you're wrong and someone gets hurt — or a business is ruined?"**
→ *"Both directions are addressed. No location is tiered above moderate on fewer than k
independent sources; no individual business is named; tiers are relative and labelled as
such in the interface; `insufficient_data` is visually distinct from `low` so absence of
evidence is never rendered as safety; and there is a stated takedown channel."*
