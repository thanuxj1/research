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
| Destinations | 294 across 19 of 22 districts (308 before place_id merging) |
| Scorecards | 1,131 destination-aspect results |
| Storyboard | 727 items collected; 335 shown across 103 destinations (the rest withheld: their text does not name the destination) |
| Coordinates | 142 destinations (OpenStreetMap) + a 64x96 SRTM terrain grid |

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
   comparisons, *not* verified accuracy. This is the single highest-value
   outstanding task, and it is the one thing in this repository that cannot be
   automated — labels produced by the same process that built the classifiers
   would restore the exact circularity they exist to remove.

   The tooling is ready and tested end to end:

   ```bash
   python scripts/35_annotate.py               # ~20 min for 200 rows
   python scripts/35_annotate.py --annotator 2 # the second pass
   python scripts/05_check_goldset.py          # progress + Cohen's kappa
   ```

   The annotator writes after every row, so it is interruptible and resumable.
   Two faults were found and fixed while testing this path: the checker read a
   different file than the annotator writes, and it crashed on the focused
   set's four aspect columns. Both would only have surfaced *after* someone
   spent the hour.
2. **Three hand-written correction rules are measured for impact, not
   accuracy.** `scripts/33_ablate_rules.py` switches each off and rebuilds the
   tree (`reports/rule_ablation.json`):

   | rule off | safety rate | worst aspect |
   |---|---|---|
   | *(none — deployed)* | 50.9% | safety |
   | request rule | 48.8% | safety |
   | **safety recall** | **46.7%** | **price & value** |
   | site rule | 50.9% | safety |
   | all three | 44.1% | price & value |

   **The headline claim depends on a single rule.** Switching off the safety
   recall alone drops safety below price & value. Whether the 215 labels it
   flips are *correct* still needs #1 — impact is not accuracy.

   The domain patch, listed here previously as a third risk, is **not
   deployed**: it feeds `pol_hybrid` (Method C), a comparison column, while
   the tree is built from `pol_final`.
3. ~~**Known label errors.**~~ Both measured and addressed. The war-memorial
   case ("soldiers who died" as a safety complaint) no longer occurs — 0 such
   segments are counted as complaints. The site-rule case was real: 18
   regulations ("prohibited to take polythene inside the park") were counted
   as cleanliness complaints. `polarity.site_rule_is_not_a_complaint` now
   marks them neutral, worth 0.3 pp of the cleanliness rate. It stands down
   when a hazard word is present, so "not allowed to swim, the current is
   dangerous" keeps its negative label.
4. **No quote can be traced to its original review, and the API will not
   fix it.** Neither corpus preserved a review URL. All 308 destinations now
   carry a Google `place_id`, but that identifies the PLACE, not a review.
   Two separate blockers, both verified:

   - `collect_places` in `collect.py` still calls the **legacy** Places
     endpoints, which return `REQUEST_DENIED` on any Cloud project created
     after Google's 2025 cutover.
   - Porting it would not help. On Places API (New), asking for the `reviews`
     field returns **HTTP 200 with the field silently absent** — no error, no
     data. Tested with field mask `reviews` and with `*` (34 fields returned,
     `reviews` not among them). It is a higher-billing-tier field this project
     is not provisioned for.

   So this is a **billing** limitation, not a code one, and the collector was
   deliberately not ported: shipping one that returns zero reviews would be
   worse than leaving the problem stated. What the API *does* return —
   `rating` and `userRatingCount` — is used instead, see external validity
   below.
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
python scripts/30_resolve_place_ids.py --limit 20        # needs GOOGLE_MAPS_API_KEY
python scripts/32_collect_elevation.py                   # free, no key
```

`30_resolve_place_ids.py` asks Google for the `place_id` behind each
destination name, so that merging two spellings into one place rests on an
external identifier rather than on our string key. All 308 destinations are
resolved; the cache makes re-runs free.

It proposes, and a person decides. Three guards hold a group back for reading
rather than merging it: variants sharing no identifying word, a Google name
that matches none of ours, and variants filed under different districts. The
last one earned its place immediately — `Maritime Museum` (204 reviews, filed
under Galle) resolved to the *Colombo* Port Maritime Museum, which every
name-based check had passed.

Every group gets an explicit verdict with a reason in
`reports/place_id_decisions.json`, and `--apply` refuses to run while any is
undecided. Of 15 proposed groups, 13 were merged and 2 refused: the Maritime
Museum pair above, and the Ravana Falls group, whose id points at `Kuda Ravana
Ella waterfall` — a different, smaller fall — and which had swept in a third
waterfall from another district. Those names may well be one place; this
identifier is not the evidence for it.

Result: 308 destinations to 294, with 2,212 reviews relabelled and none lost.

## External validity

`scripts/34_external_validity.py` compares our complaint rates against a
number nobody in this project produced: the public Google star rating for the
same place, and the count of ratings behind it. 300 of 308 destinations carry
one. This is **corroboration of the aggregate, not accuracy of any label** —
open problem #1 still stands.

Spearman rank correlation, complaint rate vs star rating. Negative is the
expected direction: more complaints, fewer stars.

| | rho | n | p |
|---|---|---|---|
| **overall complaint rate** | **-0.421** | 254 | <0.001 |
| Crowding & Noise | -0.370 | 166 | <0.001 |
| Cleanliness | -0.268 | 152 | 0.0008 |
| Facilities | -0.236 | 128 | 0.007 |
| Scenery | -0.209 | 252 | 0.0008 |
| Price & Value | -0.131 | 142 | 0.12 *(ns)* |
| Roads & Access | -0.128 | 160 | 0.11 *(ns)* |
| **Safety** | **-0.087** | 106 | 0.38 *(ns)* |

Two things worth reading carefully.

**The overall rate holds up.** Destinations this pipeline calls heavily
complained-about do rate lower with the travelling public, at rho = -0.42
across 254 places. That is not proof any individual label is right, but a null
or positive correlation would have been a serious warning, and it is not what
came back.

**Safety shows no detectable relationship with star ratings — and that is the
finding, not a failure.** This project already documented that **55.3% of
safety complaints sit inside reviews a star-trained model reads as positive**:
a visitor warns that the current is dangerous and still gives five stars.
If that is true, a star rating *cannot* track safety complaints, and this
independent measurement is exactly what you would predict. The same ordering
appears in both analyses — cleanliness 0.8%, roads 21.2%, safety 55.3%
contamination, against correlations of -0.27, -0.13 and -0.09.

So the weakest correlation in the table is the strongest argument in the
project: **for safety, the star rating is measuring something else, which is
precisely why aspect-based complaint mining is worth doing.**

Read the other direction, though, safety is also the aspect most dependent on
a hand-written rule (open problem #2) and the one with the fewest destinations
here (n=106). Both readings are live until the human gold set exists.

**Coverage:** our corpus size per destination correlates with the public
rating count at **rho = 0.709** — the reviews we hold track how busy a place
actually is, rather than over-sampling a convenient subset.

## The 3D map

The map has a second view: terrain, with the choropleth painted onto the
ground rather than floating over it. Click a district and the camera flies to
it; the district list does the same thing, so the two ways in agree.

It uses no mapping library, no tile server and no API key. NASA SRTM 30 m
elevation (public domain) is collected once by `32_collect_elevation.py` into a
64x96 grid -- about 30 KB, less than a single map tile -- and embedded in the
page. That is a deliberate trade against Google Maps or OSM tiles: both need a
network, and a Google key would have to ship inside a file that gets handed
around. `pipeline.py` already argues the principle -- *a static rebuild cannot
be "down"* -- and a tiled map would have made the dashboard the one thing in
the project that can be.

Two things the interface admits rather than hides. Relief is exaggerated about
22x, because at true scale a 2 km peak on a 400 km island is invisible. And
depth shrinks distant columns while near ones hide far ones, so heights are not
comparable across the map -- the flat view remains the one to read numbers
from. Both views are driven by identical data.

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
