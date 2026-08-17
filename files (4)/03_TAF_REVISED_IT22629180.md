# Revised Topic Assessment Form Text — IT22629180
**Project R26-IT-022 · Dynamic Safety Heatmap & Scam Analytics Engine**

Drop-in replacement text for your row of TAF §8, plus corrections needed in the shared
sections. Every claim below is one you can currently defend or have a concrete plan to
defend by the stated milestone. Ambiguous, unfalsifiable and unsupported claims from the
current draft are removed, with reasons given at the end.

---

## A. Your row in §8 (Objectives and Novelty)

### Sub Objective

> To develop and evaluate a demographic-conditional tourist safety intelligence engine that
> aggregates heterogeneous, differentially credible incident reports into district-level
> risk estimates that are exposure-normalised, credibility-weighted, temporally decayed,
> and confidence-gated — and that decline to produce a risk value where the evidence base
> is insufficient. The component's distinguishing research question is whether
> victim-demographic signals can be extracted from unstructured incident text with
> sufficient reliability to condition risk estimates on traveller profile, replacing the
> assigned multipliers used in current systems with coefficients estimated from data.

### Tasks

**1. Corpus construction and characterisation.**
Aggregate incident reports from government travel advisories (UK FCDO, US State Department,
Australia Smartraveller), Sri Lankan national press, traveller review platforms, and video
transcripts. Apply a word-boundary relevance filter that logs a structured rejection reason
for every excluded item, enabling the filter's own false-negative rate to be measured from
a hand-labelled sample of 200 rejections. Freeze and hash a versioned corpus snapshot;
all reported results are computed against the snapshot rather than the live database.

**2. Incident classification and gold-set evaluation.**
Classify each record for incident presence, incident type (11-key canonical taxonomy) and
severity. Construct a 388-record hand-annotated gold set — 188 safety records and ~200
review records, evaluated and reported separately because their base rates differ. A second
annotator independently labels a random 10% and Cohen's κ is reported. Precision, recall
and F1 are reported per class for classes with support ≥ 20, against a keyword-rule
baseline and a TF-IDF + logistic regression baseline.

**3. Victim-demographic signal extraction.**
Develop a classifier that infers victim profile (solo female, solo male, couple, family,
group, unknown) from explicit textual evidence in incident reports. Evaluate by macro-F1
on classes with support ≥ 20; report the `unknown` rate as a substantive finding about how
much demographic signal free-text reporting actually carries.

**4. Statistical derivation of demographic risk conditioning.**
For each (demographic × incident type) pair, estimate the risk ratio relative to the pooled
distribution, with Wilson 95% confidence intervals and Benjamini–Hochberg correction for
multiple comparisons. Cells whose interval spans 1.0 receive a conditioning factor of 1.0
and are reported as not significant at the available corpus size. This replaces the assigned
multipliers used in comparable systems with estimated, interval-bounded coefficients.

**5. District aggregation with exposure normalisation and confidence gating.**
Aggregate reports to district polygons. Weight each report by source credibility tier and
exponential temporal decay on **publication** date, with undated records handled in a
separate bucket rather than defaulted to recent. Apply a Wilson lower bound to the incident
ratio and Bayesian shrinkage toward a global prior for small-N districts. Normalise by SLTDA
visitor-presence data where published (currently 8 of 22 polygons) and label all remaining
districts `density-only`. Assign a distinct `insufficient_data` state below a stated
minimum report count, rendered so that absence of evidence is never presented as safety.

**6. Parameter sensitivity and ablation.**
Every free parameter — decay half-life, severity/ratio weighting, shrinkage strength, prior,
and the two confidence thresholds — is swept over a pre-registered range, with Kendall τ of
the resulting district ranking against the default reported for each. Component ablation
(raw count → + credibility weighting → + temporal decay → + exposure normalisation) reports
Spearman ρ against the full model, so that any component with negligible empirical effect
at this corpus size is identified and reported as such.

**7. Evaluation of decision impact.**
A within-subject user study (n ≥ 30, counterbalanced) comparing an ungated undifferentiated
risk map against the confidence-gated, demographic-conditional interface. Primary measure
is Brier score on probabilistic safety judgements; a targeted item measures whether
participants misinterpret a no-data district as safe. Ethical clearance obtained prior to
data collection.

### Novelty

**1. Demographic conditioning derived from data rather than assigned.**
Systems and research that personalise safety information by traveller profile do so with
hand-set multipliers. This component treats the coefficients as quantities to be
*estimated* from labelled incident text, reported with confidence intervals, and set to
unity where the data do not support a difference. The contribution is the estimation
procedure and its honest reporting, not the personalisation feature itself.

**2. Victim-demographic extraction from unstructured tourism incident text.**
Demographic attributes are latent in narrative incident reports and, to the best of the
available literature, have not been extracted at scale for tourism safety. The `unknown`
rate is itself a novel measurement: it quantifies how much demographic signal this class of
source actually carries, which bounds what any profile-adaptive tourism system can achieve.

**3. Refusal as a designed system behaviour.**
Tourism platforms suppress negative signal for commercial reasons; safety systems that do
publish it typically emit a value for every location regardless of evidence. This engine
assigns an `insufficient_data` state that is visually and semantically distinct from "low
risk", and reports exposure-normalised rates only for the districts where official visitor
data exists, labelling the remainder `density-only`. The design commitment — that a
confidently wrong "safe" is worse than an honest "unknown" — is evaluated directly in Task 7.

**4. Exposure normalisation with disclosed partial coverage.**
Incident density is confounded with visitor volume; normalising by official visitor-presence
data removes the confound where such data exists. Rather than imputing values for the 14
districts SLTDA does not publish, coverage status is exposed in every API response and in the
interface, and the ablation quantifies how much the normalisation changes district ordering
on the covered subset.

**5. Live methodological transparency.**
Every constant, threshold and weighting decision is exposed at
`GET /api/v1/districts/methodology` as machine-readable JSON, alongside the corpus snapshot
hash. The methodology is an inspectable runtime artefact rather than a static claim in a
document, so a reviewer can interrogate the running system directly.

---

## B. Corrections required in the shared sections

These are group-level, but they are in *your* form and a panel will attribute them to the
whole team.

| Section | Current text | Problem | Replace with |
|---|---|---|---|
| §5 para 1 | "over 2.3 million by the end of the year… targeting 3 million tourists in 2026" | Statistics with no citations, in a section that explicitly requires references | Same figures with SLTDA / Ministry of Tourism citations; verify against the latest published SLTDA monthly report before submission |
| §5 para 2 | "insights from a local tour guide friend reveal…" | An anecdote from one unnamed person is not evidence | "Semi-structured interviews with N tourism practitioners (guides, hotel staff, coordinators) conducted under ethical clearance", or delete and rely on cited sources |
| §5 para 2 | "highlighted anecdotally on social media and tourism forums" | "Anecdotally" concedes the evidence is weak | "A preliminary content analysis of N forum threads and reviews identified the following recurring problem categories: …" |
| §5 | No references anywhere | The section header requires them | Add the reference list in §C below |
| §6 | "an AI cluster" | Not a technical term; a panel will ask what it means | "four independently evaluated AI components" |
| §6 | "real-time" (multiple) | Ingestion is scheduled daily/continuous, not real-time; scoring is per-request over stored data | "continuously updated" / "computed per request against the current corpus" |
| §6 | "Data Clustering & Analysis… identify high-risk geographical zones" | Geocoding is destination-level; clustering over ~25 snapped coordinates recovers the dictionary, not spatial structure | "aggregates reports to district polygons and reports destination-level risk with explicit confidence states" |
| §7 | "No sensitive personal information will be collected" | Inferring gender in a harassment context *is* special-category data | See §7 revision below |
| §7 | "ethical clearance may be required" | Non-committal; it *is* required (user study + demographic inference) | "Ethical clearance will be obtained prior to any data collection involving human participants or demographic inference" |
| §8 main objective | "utilizes an AI cluster including optimization algorithms, computer vision, and predictive analytics" | Vague | Name the four components and their evaluation metric each |
| Your row | "K-Means or DBSCAN" | Undecided method reads as unplanned | Commit: DBSCAN — no *k* to pre-specify, native noise handling, density-defined hotspots. Or drop clustering entirely (see removed claims) |

### §7 ethics paragraph — suggested replacement

> This component processes user-generated incident reports and infers victim-demographic
> attributes, including gender in the context of harassment reporting. These are
> special-category personal data under Sri Lanka's Personal Data Protection Act No. 9 of
> 2022, and the associated user study involves human participants. Ethical clearance will
> therefore be obtained prior to data collection. The submission will address: lawful basis
> and data minimisation for demographic inference; a corroboration threshold below which no
> location may be assigned an elevated risk tier; a prohibition on naming individual
> businesses in user-facing output; a documented correction and takedown channel; explicit
> in-interface disclosure that risk tiers are relative to the current evidence base; and
> the terms-of-service position for each data source, with API-sanctioned access preferred
> over HTML scraping wherever an API exists. The system's potential to cause economic harm
> to the honest operators of a district assigned an elevated tier is recognised and is the
> principal justification for the corroboration threshold and the no-naming rule.

---

## C. Reference list for §5

Verify each against the live source before submission and format to the department's
required style. Prefer the most recent SLTDA figures available at submission date.

**Official statistics and policy**
1. Sri Lanka Tourism Development Authority. *Monthly Tourist Arrivals Report*. SLTDA, Colombo. — for all arrival figures.
2. Sri Lanka Tourism Development Authority. *Annual Statistical Report*. — for district-level visitor presence and the footfall figures used in exposure normalisation.
3. Ministry of Tourism, Sri Lanka. *Tourism Vision / Strategic Plan*. — for the 2026 target figure.
4. UNWTO. *World Tourism Barometer*. UN Tourism, Madrid. — for regional recovery context.
5. Government of Sri Lanka. *Personal Data Protection Act, No. 9 of 2022*. — cited in the ethics section.

**Tourism safety, crime and destination risk**
6. Literature on tourism and crime / tourist victimisation — establishes that tourists are differentially victimised and that reporting rates are low. (e.g. work by Brunt, Mawby, Pizam and colleagues on tourist victimisation and destination crime.)
7. Literature on perceived risk in destination choice — establishes that safety perception drives destination selection and spending, which is your economic-impact argument.
8. Literature on tourism-related fraud and consumer deception in developing destinations — for the scam typology.

**Method**
9. Wilson, E. B. (1927). Probable inference, the law of succession, and statistical inference. *JASA*, 22(158), 209–212. — the interval used for small-N ratios.
10. Ester, M., Kriegel, H.-P., Sander, J., & Xu, X. (1996). A density-based algorithm for discovering clusters in large spatial databases with noise. *KDD-96*. — DBSCAN.
11. Small-area estimation / crime-mapping methodology — for the minimum-N convention behind the confidence thresholds, and for the exposure-denominator argument.
12. Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery rate. *JRSS-B*, 57(1), 289–300. — multiple-comparison correction.
13. Cohen, J. (1960). A coefficient of agreement for nominal scales. *Educational and Psychological Measurement*, 20(1), 37–46. — inter-annotator agreement.
14. Brier, G. W. (1950). Verification of forecasts expressed in terms of probability. *Monthly Weather Review*, 78(1), 1–3. — the calibration metric for RQ5.

**Comparable systems** — cite 2–3 existing tourist-safety or crime-mapping applications and state precisely what each does not do (no exposure normalisation / no confidence gating / no demographic conditioning). A novelty claim is only as strong as the comparison set behind it.

---

## D. Claims removed from the current draft, and why

| Removed claim | Reason |
|---|---|
| "Granular 'Micro-Location' Scam Detection… a specific fraudulent shop or a street corner" | Geocoding is a ~25-entry destination dictionary. No venue- or street-level coordinate exists in the corpus. A reviewer can falsify this by opening one file. Also creates a defamation exposure if a real shop is ever named. |
| "sociologically aware safety tool that is rarely observed in technical tourism research" | Unfalsifiable and uncited. Replaced with a specific, checkable claim about estimated vs assigned coefficients. |
| "The most significant contribution is the personalization of safety" | The corpus contains two demographic values, both "Tourists". Cannot be claimed until Tasks 3–4 produce results. Reframed as the *research question*, which is legitimate at proposal stage. |
| "real-time risk assessment tool" | Ingestion is scheduled; scoring is per-request over stored data. "Real-time" invites a question you cannot answer. |
| "Training or fine-tuning an NLP model to analyze the sentiment of reviews" | Current sentiment is an off-the-shelf model with TextBlob and keyword fallbacks. Either commit to fine-tuning with a stated dataset and metric, or describe what is actually used. |
| "scrape and aggregate reviews from various travel sources" | Presented without terms-of-service or ethics treatment. Retained in the revised text but scoped to API-sanctioned access with an explicit ToS position. |
| Implied claim that the map shows actual Sri Lankan district safety | At 188 records, 4 districts at established confidence and 13 with none, the corpus demonstrates the method only. Your own `methodology_report()` already says this — the form should agree with the code. |

---

## E. One-paragraph version for the abstract and the viva opening

> This component addresses the fact that tourist safety risk is conditional on the
> traveller, yet existing systems emit a single risk value per location for all users, and
> those that personalise do so with assigned rather than estimated coefficients. It
> develops an engine that aggregates heterogeneous incident reports into district-level
> estimates that are credibility-weighted, temporally decayed on publication date,
> exposure-normalised where official visitor data exists, and confidence-gated so that no
> risk value is emitted where evidence is insufficient. Its central research question is
> whether victim-demographic signals can be extracted from unstructured incident text
> reliably enough to condition risk estimates on traveller profile; the conditioning
> coefficients are estimated with confidence intervals and set to unity where the data do
> not support a difference. Evaluation covers a hand-annotated gold set with
> inter-annotator agreement, ablation and sensitivity analysis over every free parameter,
> and a within-subject user study testing whether confidence gating improves traveller
> decision calibration. Results are reported against a frozen, hashed corpus snapshot and
> characterise the method rather than the safety of Sri Lankan districts.
