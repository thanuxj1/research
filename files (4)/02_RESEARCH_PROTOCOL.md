# Research Protocol — Demographic-Conditional Tourist Safety Intelligence
**IT22629180 · Component of R26-IT-022 · SafeTravel LK**

This document supplies what the current project lacks: falsifiable research questions,
stated hypotheses, a formal problem definition, an evaluation design with baselines and
metrics, sample-size justification, threats to validity, and an ethics position. It is
written so that each section can be lifted more or less directly into the proposal and
the thesis.

---

## 1. Problem statement (formal)

Tourism safety information for a destination country is distributed across heterogeneous,
unstructured, differentially credible sources: government advisories, national press,
traveller reviews, video transcripts and forum posts. Three properties make naive
aggregation invalid:

1. **Exposure confounding.** Raw incident counts are proportional to visitor volume.
   Without a denominator, the busiest destination is always ranked the most dangerous.
2. **Credibility heterogeneity.** A government advisory and an anonymous review are not
   equal evidence, but are usually pooled as if they were.
3. **Recipient heterogeneity.** Risk is not a property of a place alone. Harassment risk is
   conditional on traveller profile; a location that is unremarkable for a group can be
   materially different for a solo female traveller. Existing systems emit one number per
   place for all users.

The third is the least addressed in the literature and is the focus of this component.

**Formal statement.** Given a corpus of incident reports
$R = \{r_1 \dots r_n\}$, where each $r_i$ carries text $t_i$, source $s_i$, timestamp
$\tau_i$, and inferred location $\ell_i$, and given a traveller profile
$p \in P$, construct a mapping

$$\text{risk}: (\text{district } d, \text{ profile } p) \rightarrow [0,1] \times \text{confidence}$$

that is (a) exposure-normalised where visitor-volume data exists, (b) credibility-weighted,
(c) temporally decayed on *event* dates, (d) conditioned on $p$ using coefficients
**estimated from data** rather than assigned, and (e) **refuses to emit a value** where
evidence is insufficient.

Property (e) is a design commitment, not a limitation: in a safety context, a confidently
wrong "low risk" is worse than an honest "no data".

---

## 2. Research questions and hypotheses

Each RQ is paired with a measurable outcome. An RQ with no measurable outcome is a topic,
not a research question — this is the distinction the panel is testing for.

| RQ | Question | Hypothesis | Metric / decision rule |
|---|---|---|---|
| **RQ1** | Can victim-demographic signals be reliably extracted from free-text tourist incident reports? | H1: A fine-tuned transformer classifier attains macro-F1 ≥ 0.70 on the classes with support ≥ 20, against a hand-labelled gold set. | Macro-F1 with bootstrap 95% CI; Cohen's κ ≥ 0.70 between annotators; `unknown` rate reported as a finding. |
| **RQ2** | Do incident-type distributions differ significantly by victim demographic? | H2: The distribution of scam types conditional on `solo_female` differs from the pooled distribution (χ² test, α = 0.05), with harassment over-represented. | χ² with Cramér's V effect size; per-cell risk ratios with Wilson 95% intervals. **If H2 is not supported, that is a reportable negative result and the demographic layer is demoted to surfacing-only.** |
| **RQ3** | Does exposure normalisation change district risk ordering relative to raw incident density? | H3: Kendall τ between the exposure-normalised ranking and the raw-count ranking is < 0.7 on the 8 SLTDA-covered districts. | Kendall τ and Spearman ρ with p-values; per-district rank deltas tabulated. |
| **RQ4** | Does source-credibility weighting materially change the ranking? | H4: Spearman ρ between the credibility-weighted and unweighted rankings is < 0.9. | The existing ablation (V1→V4). **A null result here is publishable**: it demonstrates that at pilot corpus size the weighting is not the operative mechanism. |
| **RQ5** | Does a confidence-gated, demographic-conditional presentation improve traveller decision quality relative to an ungated, undifferentiated map? | H5: Participants using the gated interface show higher calibration (lower Brier score on safety judgements) and are less likely to interpret a no-data district as safe. | Within-subject user study, n ≥ 30, counterbalanced; Brier score + a targeted "no-data misinterpretation" item; Wilcoxon signed-rank. |

RQ5 is what elevates this from a systems build to research: it tests whether the design
commitments actually change human behaviour. If time is constrained, run RQ5 as a reduced
study (n = 30, single session, ~25 minutes) rather than dropping it — a small user study is
worth far more to a panel than another engineering feature.

---

## 3. Corpus specification

### 3.1 Frozen snapshot protocol

All reported results are computed against an immutable snapshot:

```
corpus_v{N}_{YYYY-MM-DD}_sha256-{first12}.jsonl
```

The SHA-256 is computed over the sorted, canonically-serialised record set and cited in
the thesis. The live pipeline continues to run, but **never** feeds a reported number.
`RESEARCH_MODE=true` disables the startup scraper and scheduler.

### 3.2 Current snapshot (v1) — stated honestly

| Property | Value |
|---|---|
| Records | 188 |
| Scam-flagged / advisory | 107 / 81 |
| With coordinates | 176 (93.6%) |
| Distinct districts represented | 12 of 25 |
| Districts at `established` confidence (≥15) | 4 — Colombo, Kandy, Nuwara Eliya, Galle |
| Districts with **no** data | 13 |
| Colombo share | 39.4% |
| `risk_level = 3` records | 14 (7.4%) |
| Tier-0 (government advisory) records | **0** |
| Records sharing the bulk-ingestion timestamp | 70 (37.2%) |

### 3.3 Target snapshot (v2) — with acceptance criteria

Do not state "more data" as a goal. State thresholds and how they will be met:

| Target | Value | Rationale | Method |
|---|---|---|---|
| Total records | ≥ 800 | 20+ districts at ≥ 15 reports | Extend collection window; TripAdvisor yield extraction |
| Tier-0 records | ≥ 30 | Populate the top credibility tier, which is currently empty | Direct FCDO / State Dept / Smartraveller advisory ingestion via `ADVISORY_OVERRIDE` (M3) |
| `has_publish_date` coverage | ≥ 70% | Below this, temporal decay cannot be claimed | Publication-date extraction from article metadata; undated records bucketed separately |
| Districts at `established` | ≥ 15 of 25 | Cross-district comparison becomes meaningful | Targeted gap-filling queries (`fill_coverage_gaps.py`) |
| Colombo share | ≤ 25% | Reduce dateline attribution bias | Geocoding audit + `body_mention` exclusion |
| Labelled gold set | 388 records | See §5.1 | Two-annotator protocol |

**State v1 results as pilot results.** Do not wait for v2 to have findings — a
well-characterised pilot with honest limits beats an uncharacterised larger corpus.

---

## 4. Method specification

### 4.1 Pipeline

```
Sources → Relevance filter (v2, word-boundary, auditable)
        → Incident classification (is_incident, scam_type, risk_level)
        → Demographic extraction (victim_profile)          ← RQ1
        → Geocoding (destination-level, confidence-banded)
        → District aggregation (Wilson + shrinkage + decay) ← RQ3, RQ4
        → Demographic conditioning (derived ratios)         ← RQ2
        → Confidence gating → presentation                  ← RQ5
```

### 4.2 Scoring (single source of truth: `district_engine.py`)

For district $d$ with reports $r_1 \dots r_n$:

$$w_i = e^{-\lambda \Delta t_i} \cdot c(s_i), \qquad \lambda = \frac{\ln 2}{H}$$

where $H$ is the half-life in days and $c(s_i) \in [0,1]$ the source credibility weight.
$\Delta t_i$ is computed from **publication date**; records without one are excluded from
the decayed term and reported separately.

$$E = \sum_i w_i, \qquad I = \sum_{i \,:\, \text{scam}} w_i \cdot \frac{\text{risk}_i}{3}$$

$$\text{severity} = \frac{I}{|\{i : \text{scam}\}|}, \qquad \rho = \text{WilsonLower}\!\left(\frac{I}{E},\, n\right)$$

$$\text{base}(d) = \beta \cdot \text{severity} + (1-\beta) \cdot \rho, \qquad \beta = 0.70$$

$$\text{score}(d) = \frac{n \cdot \text{base}(d) + \alpha \cdot \pi}{n + \alpha}$$

**Every one of $H$, $\beta$, $\alpha$, $\pi$ is a free parameter and must be defended by
sensitivity analysis, not by assertion.** Current values ($H=180$, $\beta=0.70$,
$\alpha=0.05$, $\pi=0.30$) are the starting point; $\alpha = 0.05$ is almost certainly too
small to do anything (see audit M4). Report a table of Kendall τ against the default
ranking for each parameter sweep, and select values from that table.

Exposure adjustment applies only where SLTDA footfall exists (8 of 22 polygons); every
response carries `exposure_status ∈ {official, unavailable}` and the UI marks the latter
`density-only`.

### 4.3 Demographic conditioning (RQ1 → RQ2)

Replace the hand-set multiplier table with estimated ratios. For demographic $p$ and scam
type $k$:

$$\text{RR}(p,k) = \frac{P(k \mid p)}{P(k)}$$

reported with a Wilson 95% interval on each proportion. **Decision rule:** if the interval
for $\text{RR}(p,k)$ contains 1.0, the multiplier is set to 1.0 and the cell is reported as
*not significant at this corpus size*. Publish the full table including the non-significant
cells — showing what you could not establish is stronger than showing only what you could.

### 4.4 Confidence gating

| Reports $n$ | State | Rendering |
|---|---|---|
| $n < 5$ | `insufficient_data` | Distinct neutral colour, no tier, no score shown |
| $5 \le n < 15$ | `preliminary` | Tier shown, visually de-emphasised, labelled |
| $n \ge 15$ | `established` | Full rendering |

Cutoffs follow small-area estimation convention (a ratio from $n<5$ is not treated as a
rate). They are design parameters and must be *stated as such* — and included in the
sensitivity sweep.

---

## 5. Evaluation design

### 5.1 Gold set (addresses B2)

| Property | Value |
|---|---|
| Corpus A | 188 safety DB records |
| Corpus B | ~200 review records |
| Reported | **Separately** — the two have different base rates; pooling hides that |
| Annotators | 2; second annotates a random 10% (~40 records) |
| Agreement | Cohen's κ on `gold_is_scam`, target ≥ 0.70, reported regardless of value |
| Ambiguity | `gold_confidence = low` records excluded from metrics, count reported |
| Fields | `gold_is_scam`, `gold_scam_type`, `gold_location`, `gold_victim_profile`, `gold_confidence`, `notes` |

Annotate `gold_victim_profile` on the same pass — one annotation effort funds both RQ1 and
RQ2.

**Sample-size justification.** A 95% Wilson interval on a proportion near 0.85 at n=388 has
half-width ≈ ±3.6 pp — sufficient for claims of the form "precision exceeds 0.75",
insufficient for per-class F1 on rare classes. **Report per-class metrics only where
support ≥ 20**; list the excluded classes and their support.

### 5.2 Baselines (mandatory — a result without a baseline is not a result)

| ID | Baseline | Tests |
|---|---|---|
| B0 | Majority class | Floor for classification |
| B1 | Keyword rules (current `SCAM_TAXONOMY`) | Does ML beat the rules it replaces? |
| B2 | Raw incident count per district | Does any weighting beat counting? (RQ3, RQ4) |
| B3 | TF-IDF + LogisticRegression | Does the transformer earn its cost? |
| B4 | Uniform demographic multipliers (all 1.0) | Does conditioning change anything? (RQ2) |
| B5 | Published tourism-safety index (where available) | External validity |

The existing `ablation_study.py` covers V1→V4 for B2; fix the import (audit m1) and align
the aggregation unit to district before running.

### 5.3 Metrics by component

| Component | Primary metric | Also report |
|---|---|---|
| Relevance filter | Precision on accepted; **FNR from a 200-record rejection sample** | Rejection reason distribution |
| Incident classification | Macro-F1 per corpus | Per-class P/R/F1/support, confusion matrix |
| Demographic extraction | Macro-F1 on support ≥ 20 classes | `unknown` rate, κ |
| Geocoding | District accuracy **per confidence band** | Colombo-specific accuracy from 60-record audit |
| District scoring | Kendall τ / Spearman ρ vs each baseline | Rank deltas per district, parameter sensitivity |
| LLM advisor | Hallucination rate on 50 grounded questions | Groundedness, hedging appropriateness |
| End-to-end (RQ5) | Brier score | No-data misinterpretation rate, SUS, task time |

### 5.4 User study protocol (RQ5)

Within-subject, counterbalanced. n ≥ 30 (≥ 15 with international travel experience).
Condition A: ungated undifferentiated map. Condition B: confidence-gated,
demographic-conditional map. 8 judgement tasks per condition, drawn from districts spanning
all confidence states, **including at least two `insufficient_data` districts** — the
critical item is whether participants read "no data" as "safe".

Measures: Brier score on probabilistic safety judgements; a direct no-data
misinterpretation item; SUS; task time; free-text trust rationale. Analysis: Wilcoxon
signed-rank on paired Brier scores; McNemar on the misinterpretation item. Ethics approval
required — see §7.

---

## 6. Threats to validity

### Internal
- **Circular labelling.** Model labels used as ground truth inflate every metric. *Mitigated by* the gold set; the offending script retains its warning banner as a documented baseline.
- **Filter-induced selection bias.** Nationality and political-vocabulary exclusions systematically remove press-reported incidents and all government advisories (audit M3). *Mitigated by* `strict_filter_v2` and a measured rejection sample.
- **Dateline attribution.** Colombo over-representation from bylines rather than incident locations. *Mitigated by* the 60-record audit and `body_mention` exclusion.
- **Ingestion-date decay.** 37% of records share the bulk-load timestamp, defeating temporal decay. *Mitigated by* publication-date extraction and a separate undated bucket.

### External
- **Pilot corpus.** 4 districts at established confidence, 13 with no data. Findings characterise the *method*, not Sri Lankan safety. Must be stated in the abstract.
- **Anglophone source bias.** Sinhala- and Tamil-language sources are absent, so the corpus over-represents Western traveller experience and under-represents incidents reported locally. State this; it is a real limitation and naming it pre-empts the question.
- **Reporting bias.** Harassment is systematically under-reported; the corpus measures *reporting*, not *incidence*. Every risk figure should be read as "reported risk".

### Construct
- **Relative tiering.** Quantile tiers guarantee 25% of scored districts are "Severe" regardless of absolute risk. A district can be Severe while objectively safe. Must be disclosed in the UI next to the tier label, not only in the thesis.
- **Volume proxies in the composite.** Diversity (20%) and credibility count (15%) track how much is *written about* a place, reintroducing exposure confounding at 35% weight (audit M5).
- **Severity from 14 records.** `risk_level=3` appears 14 times and drives 70% of the district score.

### Conclusion
- **Multiple comparisons.** Testing many (demographic × scam type) cells inflates false-positive risk. Apply Benjamini–Hochberg FDR correction and report both raw and adjusted p-values.
- **Parameter freedom.** $H$, $\beta$, $\alpha$, $\pi$ and three thresholds are researcher-chosen. Pre-register the sweep ranges before running, and report the full sweep, not the best cell.

---

## 7. Ethics and responsible deployment

**Ethical clearance is required**, on two independent grounds: (i) the RQ5 user study
involves human participants; (ii) the system infers and stores demographic attributes —
including gender in the context of harassment — which is special-category personal data
under Sri Lanka's PDPA (No. 9 of 2022).

Commitments to state in the ethics submission and implement in code:

1. **Corroboration threshold.** No location is tiered above `moderate` on fewer than $k$
   independent sources, $k$ stated numerically and enforced in `district_engine`.
2. **No named entities.** No individual business, guesthouse, driver or shop is named in
   user-facing output. Aggregation floor is destination-level.
3. **Right of reply.** A stated takedown/correction channel, documented in the app.
4. **Relative-tiering disclosure.** Every tier badge carries the qualifier that tiers are
   relative to the current evidence base — in the interface, not only the thesis.
5. **No-data is not safety.** `insufficient_data` renders in a visually distinct neutral
   state and never as green. This is already implemented; keep it and cite it.
6. **Demographic data minimisation.** Traveller profile is used transiently for ranking and
   is not persisted against an identifier; extracted victim profiles are stored as
   aggregate counts, not per-record attributes linked to identifiable text where avoidable.
7. **Source terms.** State the position on each scraped platform's ToS, and prefer
   API-sanctioned access (Reddit API, YouTube Data API, Google Places) over HTML scraping
   wherever an API exists.
8. **Community harm.** Acknowledge that a Severe tier imposes economic cost on an entire
   district's honest operators, and that this asymmetry justifies the corroboration
   threshold and the no-naming rule.

---

## 8. Deliverables and contribution statement

**Artefacts:** frozen corpus snapshot (hashed); annotated gold set with κ; demographic
extraction model + metrics; district scoring engine with live methodology endpoint;
sensitivity and ablation results; RQ5 study data; reproducibility package (snapshot +
seeds + scripts + environment).

**Contribution statement — write it this way:**

> This work contributes (i) a method for extracting victim-demographic signals from
> unstructured tourist incident reports and an empirical characterisation of how incident
> type varies by traveller profile; (ii) a confidence-gated, exposure-normalised district
> risk aggregation that declines to score where evidence is insufficient; and (iii) an
> evaluation of whether such gating improves traveller decision calibration relative to an
> undifferentiated risk map. Results are demonstrated on a pilot corpus of N reports
> covering M districts at established confidence; the corpus establishes the viability of
> the method and does not support conclusions about the relative safety of Sri Lankan
> districts.

That final clause is not a weakness. It is the sentence that tells the panel you understand
the difference between a system and a result.
