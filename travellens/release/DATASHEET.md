# TravelLens LK — Dataset Datasheet

Generated 2026-08-25.

## 1. What this is

Aspect-level opinion labels for tourist reviews of Sri Lankan destinations.
Each row records that one sentence expressed a complaint, a compliment, or a
plain fact about one topic at one place.

| | |
|---|---|
| Labelled rows | 99088 |
| Distinct sentences | 78568 |
| Destinations | 308 |
| Districts | 19 |
| Aspects | 7 |
| Complaint / praise / factual | 10353 / 38101 / 23934 |

## 2. Where the reviews came from

- **kaggle_2024_03** — 30,705 reviews
- **tripadvisor** — 16,149 reviews

Full provenance, including one source that could not be traced, is in
`SOURCES.md`. **Neither source corpus preserved review URLs**, so individual
quoted sentences cannot be linked back to the original review. Destination-level
search links are provided instead. Reviews collected by this project after
release carry a `source_url`.

## 3. What was removed, and why

| Stage | Rows left | Removed |
|---|---|---|
| loaded | 37,415 |  |
| drop missing fields | 37,326 | 89 |
| drop empty after norm | 37,288 | 38 |
| drop too short | 31,012 | 6276 |
| drop duplicates | 30,705 | 307 |

17.85% of reviews are truncated mid-sentence by the source platform's
"read more" behaviour. They were **kept and flagged**, not dropped; testing
found their complaint rates differ from untruncated reviews by under one
percentage point, in both directions, so truncation does not bias the results.

## 4. How the labels were produced

Reviews are split into single-opinion sentences, assigned to topics, then
classified as complaint / praise / factual. Topic extraction is chosen **per
aspect by measurement**, not by preference:

| Aspect | Extractor | F1 | Test positives |
|---|---|---|---|
| roads_access | trained | 0.914 | 33 |
| facilities | trained | 0.773 | 21 |
| safety | safety_model | 0.755 | 22 |
| cleanliness | rules | 0.901 | 36 |
| price_value | rules | 0.976 | 21 |
| crowd | rules | 0.903 | 16 |
| scenery | rules | 0.906 | 25 |

Polarity uses `cardiffnlp/twitter-roberta-base-sentiment-latest` with two
documented correction rules. A model trained on star-derived weak labels
scored higher in aggregate (macro-F1 0.797 vs 0.691) but inverted 55% of
safety complaints, and is **excluded from the pipeline** for that reason.

## 5. Limitations — read before using

1. **No independent human validation.** Every evaluation set in this release
   was labelled by the system's own author. The scores are internally
   consistent comparisons, **not** verified accuracy. An independently
   annotated gold set is the outstanding work.
2. **Complaint rate is not risk.** It is the share of *expressed opinions*
   that are negative. People rarely praise a road that simply worked, so
   every aspect is biased toward complaint once mentioned. Compare rates
   *between* destinations; never read one as a probability of a bad visit.
3. **Platform, not nationality.** Of 16,156 TripAdvisor reviewers exactly one
   lists Sri Lanka as home; the Google corpus has no reviewer-origin field at
   all. Differences between the corpora are **platform** differences. The
   domestic-versus-international reading is an interpretation, not a finding.
4. **Coverage.** 19 of 22 districts. Monaragala, Puttalam and the Vanni have
   no reviews in either corpus.
5. **Three hand-written correction rules** remain unvalidated: a domain patch,
   a polite-complaint rule and a safety recall rule. Each was written in
   response to an observed failure; none has been measured against
   independent labels.
6. **Time.** Reviews span 2011–2024. Testing found a destination's historical
   complaint rate predicts its current one at r≈0.6, *flat* from one to seven
   years, so no recency weighting is applied. A resolved problem still
   appears in the data until newer reviews outnumber older ones.

## 6. What this must not be used for

- **Safety decisions.** Safety labels are the least reliable in the set
  (F1 0.755, the lowest of seven) and the corpus records opinions, not
  incidents. Do not use it to decide whether a place is safe to visit.
- **Ranking or penalising individual businesses or operators.**
- **Any claim about Sri Lanka as a whole.** Three districts are absent.
- **Redistribution of the underlying review text.** Excerpts here are
  quotation-length evidence; the full corpora belong to their original
  collectors.

## 7. Files

| File | Contents |
|---|---|
| `enriched_labels.csv` | One row per (sentence, aspect) with its label |
| `scorecards.csv` | One row per (destination, aspect) with counts and rates |
| `evaluation_sets/` | The author-labelled test sets, with their labels |
| `SOURCES.md` | Provenance for every input, including unresolved gaps |
| `DATASHEET.md` | This file |

## 8. Citing the models used

Two pretrained models are applied and are **not** contributions of this work:
`distilbert-base-uncased-finetuned-sst-2-english` and
`cardiffnlp/twitter-roberta-base-sentiment-latest`. District boundaries are
CC-BY from `thejeshgn/srilanka`, derived from GADM 2.7 — attribution required.