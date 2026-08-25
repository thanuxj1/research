# LostinSriLanka

Aspect-based complaint mining for Sri Lankan tourist destinations.

Reads 46,854 tourist reviews and answers one question: **what do visitors
complain about, and where?** A star rating tells you people liked a place; it
never tells you the road was broken, the toilets were locked or the swimming
spot was dangerous.

**Live dashboard:** https://claude.ai/code/artifact/9ed617c0-38ca-498c-bc4f-82df0a79f48e

---

## What exists

| | |
|---|---|
| Reviews | 46,854 (Google Maps 30,705 + TripAdvisor 16,149) |
| Sentences labelled | 78,568 → 99,088 (sentence, aspect) rows |
| Destinations | 307 across 19 of 22 districts |
| Scorecards | 1,150 destination-aspect results |
| Storyboard | 731 items (316 videos, 415 news) across 178 destinations |
| Coordinates | 143 destinations (OpenStreetMap) |

---

## Running it

```bash
# one-time
pip install -r requirements.txt -r requirements-train.txt

# rebuild everything from the corpus (~15 s, model outputs are cached)
python scripts/10_refresh.py

# load to SQLite
python scripts/29_load_db.py

# package the citable release
python scripts/24_release.py
```

The dashboard is a single self-contained file: `dashboard/index.html`. No
server, no database, no internet beyond a web font. Rebuild it with
`python scripts/08_build_dashboard.py`.

---

## The pipeline

```
reviews
  → 02 segment          split into single-opinion sentences (65% carry >1 opinion)
  → 03 tag aspects      rule lexicon, 7 aspects
  → 17 embeddings       sentence-similarity tagger
  → 19 trained tagger   classifier trained on lexicon labels
  → 06 polarity         complaint / praise / factual
  → 07 aggregate        country → district → destination → aspect → quotes
  → 08 dashboard        one HTML file
```

### Which extractor handles which aspect

Chosen **per aspect by measurement**, never by preference. Each was evaluated
on a purpose-built test set measuring precision *and* recall:

| Aspect | Extractor | F1 | Test positives |
|---|---|---|---|
| Price & Value | rule lexicon | 0.976 | 21 |
| Scenery | rule lexicon | 0.906 | 25 |
| Crowding | rule lexicon | 0.903 | 16 |
| Cleanliness | rule lexicon | 0.901 | 36 |
| Roads & Access | trained classifier | 0.914 | 33 |
| Facilities | trained classifier | 0.773 | 21 |
| Safety | dedicated classifier | 0.755 | 22 |

The headline finding: **for four of seven aspects the lexicon wins outright**,
once its vocabulary gaps are fixed. Those gaps — not the method — were the real
problem. The safety lexicon had no entry for `safe`, so every warning phrased
"not safe to swim" was invisible. Patching it moved safety 0.522 → 0.741,
cleanliness 0.643 → 0.901, price 0.632 → 0.976.

Models win only where meaning genuinely outruns vocabulary: roads (many
phrasings, few shared words) and safety (rare and lexically diverse).

---

## Things that are deliberately NOT done

**A model trained on star ratings is excluded from the pipeline.** It scored
higher in aggregate (macro-F1 0.797 vs 0.691) and inverted **55% of safety
complaints** — "don't bath in beach because it's dangerous" came out as praise.
A star rates the whole review, so a warning inside a five-star review is
labelled positive. The damage scaled with how often an aspect is criticised
inside otherwise-positive reviews: cleanliness 0.8%, roads 21.2%, safety 55.3%.
It is kept for comparison behind `use_trained=False` in `aggregate.py`.

**No recency weighting.** An earlier version applied invented decay weights.
Measurement showed a destination's historical complaint rate predicts its
current one at r≈0.6, *flat* from one year to seven — so age alone does not make
a review less informative and down-weighting would discard valid evidence.
Per-destination timelines are published instead.

**Storyboard media never enters a calculation.** Videos and news articles are
displayed beside a destination and never counted. This is enforced by
`tests/test_media_separation.py`, which writes a media row, rebuilds the whole
tree and asserts every count and rate is unchanged.

---

## Open problems

1. **No independent human validation.** Every evaluation set was labelled by
   the assistant that built the pipeline. The scores are internally consistent
   comparisons, *not* verified accuracy. `reports/goldset_focused_annotator1.csv`
   is 200 rows, ~46 minutes, and is the single highest-value outstanding task.
2. **Three hand-written correction rules are unmeasured** — a domain patch, a
   polite-complaint rule and a safety recall rule.
3. **Known label errors** found by querying the database: a war-memorial
   description ("soldiers who died") counted as a safety complaint; site rules
   ("no polythene allowed") counted as cleanliness complaints.
4. **Google Maps API key is a placeholder.** Fixing it unlocks reviews *with
   source URLs* — neither existing corpus preserved any, so no quote can
   currently be traced to its original review.
5. **Reddit needs an app registration**; the public JSON endpoint returns 403.
6. **Three districts have no data**: Monaragala, Puttalam, the Vanni.

---

## Collection

Everything was collected through documented public interfaces. Nothing scrapes
a site whose terms prohibit it.

```bash
python scripts/23_collect.py --what youtube --limit 90   # needs YOUTUBE_API_KEY
python scripts/28_collect_news_targeted.py --limit 320   # free, no key
python scripts/25_collect_open.py --what osm --limit 320 # free, no key
python scripts/26_collect_reddit.py                      # needs an app
```

Targeted news searches *for each destination by name*, so the article's subject
is known rather than inferred. The earlier untargeted approach matched
"community" to the Community Tsunami Museum and "parliament" to the Old
Parliament Building — 3 wrong out of 4.

---

## Layout

```
src/travellens/     pipeline modules, one per stage
scripts/            numbered entry points, run in order
reports/            evaluation sets, scores, gold sheets, annotation guidelines
dashboard/          template.html (source) + index.html (built)
release/            citable bundle + DATASHEET.md + SOURCES.md
data/processed/     working files (mostly gitignored, regenerable)
tests/              separation guarantees
```

Every threshold and routing decision is documented **in the code, beside the
thing it controls**, with the measurement that justified it. If a number looks
arbitrary, the comment above it explains where it came from — or says plainly
that it was assumed and needs validating.
