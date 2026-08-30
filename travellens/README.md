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

Two commands.

```bash
pip install -r requirements.txt -r requirements-train.txt

python scripts/49_build_all.py     # rebuild every artefact, in order
python scripts/50_launch.py        # check it, then serve all of it
```

That serves the whole system on one port, as **one page with three tabs**:

| | |
|---|---|
| `http://localhost:8778/` | the app &mdash; **Map**, **Stories & videos**, **Add a review** |
| `http://localhost:8778/#stories` | any tab is directly linkable |
| `http://localhost:8778/dashboard` | the map on its own, if you want it standalone |
| `http://localhost:8778/docs` | the API |

**One process.** The portal calls the API on its own origin, so there is no
CORS to configure and no second server to remember. It used to be three things
to start, and a reader who opened `portal/index.html` from disk got a page that
looked finished and did nothing, with the reason buried in a browser console.

`49_build_all.py` calls the numbered scripts rather than reimplementing them,
so each stage still has exactly one implementation and any of them can be
re-run alone (`--only 45` runs just the portal build). It stops at the first
failure, because later stages read what earlier ones write.

### Preflight

`50_launch.py` checks before it serves, and fixes nothing. Each check compares
two things that must agree and names the command that reconciles them:

```
  ok  dashboard is current             built after the tree
  ok  portal is current                built after the tree
  ok  evidence threshold               suppress below 10 (reliability says 10 or more)
  ok  accuracy coverage                7 of 7 aspects measured
  ok  submission store                 local SQLite (user_submissions.db)
```

The first two matter most. Both pages are static files with the numbers baked
in, so rebuilding the tree and forgetting to rebuild a page leaves it showing
yesterday's figures and looking entirely normal doing it. Nothing downstream
can catch that; a timestamp comparison can. Run the checks alone with
`--check`.

**One combination is refused outright.** If `SUBMISSIONS_DATABASE_URL` is set,
every `POST /analyse` writes to the hosted research corpus. Bound to loopback
that is a deliberate choice. Bound to `0.0.0.0` it publishes a write endpoint
into the data this thesis rests on, so `--host` outside loopback with that
variable set will not start.

### What gets stored, and who can change it

Everything a contributor creates goes to the submissions database and stays
there across restarts: reviews and their segment analysis, corrections, and
stories. `SUBMISSIONS_DATABASE_URL` sends them to Postgres; unset, they go to
`user_submissions.db`. Both paths run the same schema.

| | create | read | update | delete |
|---|---|---|---|---|
| review | `POST /analyse` | `GET /reviews`, `GET /reviews/{id}` | — | `POST /reviews/{id}/withdraw` |
| story | `POST /stories` | `GET /stories` | `PATCH /stories/{id}` | `DELETE /stories/{id}` |
| correction | `POST /corrections` | `GET /corrections` | — | — |

**Ownership without accounts.** The portal asks for no name and no email, and
adding a login so an edit button could work would collect more about a
contributor than their review does. So editing rights ride on a token returned
once at creation and never stored: only its SHA-256 hash is kept, compared in
constant time, and required in `X-Manage-Token`. A copy of the database does not
let anybody edit anyone's content, and rows created before tokens existed are
unmanageable rather than open to everybody.

**A review is withdrawn, not deleted.** `DELETE` would orphan its segments and
silently move every figure derived from them with no record that anything had
been there. Withdrawal stamps `withdrawn_at`, and the row leaves every listing
and every count -- including the segment counts behind the complaint rates,
which is why `/stats` joins the two tables. A story is display-only content
that never entered a calculation, so deleting one really deletes it.

**Nothing vanishes on refresh.** The browser keeps a list of what it has sent,
with the tokens, in `localStorage`. The *Add a review* tab shows it as **Your
submissions**, so a review is still on screen tomorrow, with a Withdraw button
beside it. That list is local -- the server has no idea who you are, which is
the point -- so clearing site data loses the ability to withdraw. Stories you
wrote show a Delete button for the same reason and only in the browser that
wrote them.

### Why the map tab is a frame

The Map tab hosts `dashboard/index.html` in an iframe rather than inlining its
markup, and that is an engineering decision rather than a shortcut.

The two documents share seven CSS class names -- `.card`, `.wrap`, `.num`,
`.warn`, `.masthead` and others -- and the dashboard styles bare `body`,
`table`, `th`, `td`, `button` and `input`. Merged into one document, each would
silently restyle the other: the dashboard's table rules would land on the
portal's baseline panel, its `button` and `input` rules on the submission form.
Framed, each keeps its own stylesheet.

It also keeps `dashboard/index.html` a valid standalone file, which is a
property this project protects elsewhere -- the map still opens from disk with
no server at all. `tests/test_app_tabs.py` asserts the collision that justifies
the frame, so if somebody later inlines the two the test says why not.

The frame gets its `src` only when the Map tab is first opened, so the other
two tabs do not pay for 3.8 MB they are not showing. The dashboard removes its
own link back to the portal when it detects it is framed; without that, the
link would load the whole app inside its own map panel.

### The pages on their own

Both are still self-contained single files, and still work opened directly from
disk with no server at all -- `dashboard/index.html` fully, and
`portal/index.html` (the three-tab app) in read-only form until it can reach an
analyser (point it at one with `?api=http://host:port`). Opened from disk the
Map tab still works, because the frame path is relative. The dashboard needs no internet beyond a
web font and the Wikipedia photo lookup, neither of which any figure depends on.

```bash
python scripts/10_refresh.py       # re-derive from the raw corpus (~15 s, cached)
python scripts/29_load_db.py       # load to SQLite
python scripts/24_release.py       # package the citable release
```

## Evidence thresholds, measured

The dashboard refuses to print a rate below `MIN_MENTIONS_DISPLAY` opinions and
marks one "low confidence" below `MIN_MENTIONS_CONFIDENT`. Those were **5 and
15 -- two numbers chosen because they felt about right**, guarding every figure
on the page.

`scripts/46_reliability.py` measures them. A complaint rate has no ground truth
-- nobody has ever counted the true cleanliness complaint rate at Kandy Lake --
so it cannot be validated by comparison. It is validated by **reproducibility**:
split each destination-aspect cell's opinions in half at random, score each half
on its own, and see whether the two halves agree. Spearman-Brown corrected,
averaged over 200 splits, computed within aspect.

| opinions in the cell | cells | reliability | halves land apart by |
|---|---|---|---|
| 2-9 | 618 | **0.462** | 26.0 pp |
| 10-14 | 160 | 0.749 | 16.0 pp |
| 15-19 | 105 | 0.754 | 14.3 pp |
| 20-29 | 133 | **0.809** | 11.7 pp |
| 30-49 | 146 | 0.826 | 9.3 pp |
| 50-99 | 147 | 0.893 | 6.8 pp |
| 100+ | 141 | **0.960** | 3.7 pp |

So the thresholds are now **10 and 20**. Below 10 opinions two halves of the
same place disagree by 26 percentage points and reproduce each other at 0.46 --
publishing that rate would be publishing noise, and the old threshold of 5 sat
inside that band. 0.80 is the conventional floor for a confident group-level
measure, and the bands first clear it at 20-29, not at 15.

**The null.** A reliability figure means nothing without knowing what the same
procedure returns when there is nothing to find, so the study re-runs with
verdicts shuffled between cells: **-0.083**, flat in every size bin. Two
artefacts were caught this way and neither is obvious. Pooling cells across
aspects returned 0.53 under the null, because scenery sits near 9% and safety
near 70% and both halves of any cell agree merely by belonging to the same
aspect -- hence the within-aspect centring. Then an aspect contributing a single
cell to a subset, left uncentred, acted as a leverage outlier and returned 0.82
in the 100+ bin. Both are held by `tests/test_reliability.py`.

**What it cost.** 271 of 1,103 destination-aspect cells are no longer shown, and
the "ok confidence" set falls from 672 to 567. National aspect rates are
unchanged -- suppression governs what is displayed per destination, not what is
counted. The remaining counts match the study exactly: 832 published cells
against 832 cells at n>=10, and 567 confident cells against 567 at n>=20.

**Per aspect, cells of 10+:** crowd 0.855, cleanliness 0.843, safety 0.824,
price & value 0.816, scenery 0.807, roads & access 0.762, facilities 0.741.
Every aspect clears 0.74 and five of seven clear 0.80 -- *including the three
with no gold labels*, since reliability needs no labels. Read reliability
beside the gap, though: scenery has the smallest gap of any aspect (4.2 pp) and
scored lowest of all when small cells were included, because every scenery cell
sits near the same rate and there is almost no between-place variation left to
reproduce. A low correlation with a small gap means the aspect does not
discriminate between places, not that the estimate is imprecise.

---

## Accuracy: what the verdict is worth

`reports/gold_evaluation.json` scores whether the right ASPECT was found.
`scripts/43_evaluate_polarity.py` scores whether a correctly-found aspect got
the right VERDICT -- and the verdict is what every complaint rate is made of,
so this is the measurement that caps every accuracy claim in the project.

Part A, the representative sample:

| aspect | vs reader 1 | 95% CI | vs reader 2 | two humans agree |
|---|---|---|---|---|
| Cleanliness | 0.852 | [0.704, 0.963] | 0.958 | 0.975 |
| Facilities | 0.636 | [0.485, 0.788] | 0.679 | 0.811 |
| Safety | 0.636 | [0.364, 0.909] | 0.778 | 0.958 |
| **Roads & Access** | **0.421** | [0.211, 0.632] | 0.571 | 0.871 |
| macro | 0.636 | | **0.747** | 0.904 |
| **unanimous pairs only** | **0.718** | [0.657, 0.866] | | |

Three things here were free -- they needed no new labelling, only the labels
already collected:

**Intervals.** Safety's accuracy rests on eleven pairs and its interval spans
half the scale. Quoted bare, 0.636 reads as knowledge; quoted as
[0.364, 0.909] it reads as what it is. Claims rest on the lower bound.

**The second reader.** Two people labelled these 200 segments independently and
both recorded verdicts, not just presence, but the project had only ever scored
against annotator 1. Against annotator 2 the macro is **0.747**, not 0.636 --
the same system, a different reader, eleven points apart. That spread is a
property of the task, and reporting one number without the other hides it.

**The ceiling.** Two humans reading these sentences agree 81% to 98% of the
time. An accuracy reported against an implicit 100% asks the pipeline to beat
the people who defined the task. Read against the ceiling, cleanliness at 0.852
against 0.975 is close; roads at 0.421 against 0.871 is the real defect in this
project, and both readers agree it is one.

`unanimous_pairs` -- scored only where both readers gave the same verdict -- is
the fairest single figure at **0.718**, because a pair the two humans split on
has no defensible right answer to score against.

### Extraction precision, all seven aspects

A second pass over the same 420 pairs asked the question the polarity sheet had
no room for -- *is this sentence about that topic at all?* -- giving extraction
precision where the gold set never reached:

| aspect | precision | judged | source |
|---|---|---|---|
| Roads & Access | 0.900 | 60 | presence sheet, 1 reader |
| Crowding & Noise | 0.825 | 80 | presence sheet, 1 reader |
| Price & Value | 0.812 | 80 | presence sheet, 1 reader |
| Safety | 0.800 | 60 | presence sheet, 1 reader |
| Facilities | 0.733 | 30 | presence sheet, 1 reader |
| Scenery | 0.713 | 80 | presence sheet, 1 reader |
| Cleanliness | 0.667 | 30 | presence sheet, 1 reader |

Scenery at 0.713 finally puts a number on a problem this project had only
argued about: roughly three in ten scenery tags are on sentences that are not
about scenery, which is the "segments about traffic and litter get tagged
scenery because they contain *lake*" case, measured.

**Precision only, and deliberately so.** The sample holds nothing but pairs the
pipeline already tagged, so it cannot see a mention the pipeline missed. No
recall, therefore no F1 -- and a test fails if either is ever manufactured from
it. `reports/accuracy_all_aspects.json` carries these rows with `recall: null`
and `f1: null` rather than a number.

**The reader disagreement is here too.** Roads extraction precision is 0.588
against annotator 1 and 0.900 against the supplementary reader. Same pattern as
polarity, same direction, same reader.

### All seven aspects, measured

A second sample -- 420 pairs drawn uniformly at random from the pairs the
deployed pipeline tags, one row per (sentence, topic), labelled blind to the
system's verdict -- closes the three aspects that had no figure at all:

| aspect | accuracy | 95% CI | n |
|---|---|---|---|
| Roads & Access | 0.800 | [0.683, 0.900] | 60 |
| Scenery | 0.762 | [0.662, 0.850] | 80 |
| Safety | 0.733 | [0.617, 0.850] | 60 |
| Crowding & Noise | 0.725 | [0.625, 0.812] | 80 |
| Facilities | 0.700 | [0.533, 0.867] | 30 |
| Cleanliness | 0.633 | [0.467, 0.800] | 30 |
| Price & Value | 0.600 | [0.487, 0.700] | 80 |
| **macro** | **0.708** | | 420 |

**The reader matters more than the method.** `roads_access` scores 0.421
against annotator 1 (n=19), 0.571 against annotator 2 (n=19) and 0.800 against
the supplementary reader (n=60). Both samples are rule-lexicon tagged -- all
420 supplementary pairs pass the same rule gate the gold pairs do -- so this is
not a difference of frame. Three readers, three answers, on the same task, and
the spread between them is wider than the spread between any two *methods* this
project has compared. That belongs in any write-up of these figures, ahead of
the figures themselves.

Restricted further to the pairs a human says really **are** about the topic --
joining the two sheets -- the macro is **0.721**, against 0.708 over everything
the pipeline tags. The gap between those two is the cost of extraction error in
polarity terms, and it is small: safety moves 0.733 to 0.833 and scenery 0.762
to 0.807, but most aspects barely shift. Extraction error is real and is not
what limits the verdict.

**What the supplementary sample cannot do.** One reader, so no agreement figure
and no ceiling for the three aspects it alone covers. That reader is also the
system's author, which is the same class of limitation as open problem #1 --
mitigated but not removed by the sheet being blind, since the system's verdict
was never shown and the labelling could not be anchored on the answer being
tested. A second reader over a subset would close it, the way the focused gold
set was closed.

Regenerate or extend the sheet with:

```bash
python scripts/47_polarity_sheet.py    # writes a blank sheet
```

420 rows, roughly 85 minutes -- one row per (sentence, topic), and the reader
puts N, P or X in one column. Sampled uniformly at random from the pairs the
deployed pipeline tags, per aspect, excluding gold-set segments and truncated
text. Deliberately **not** stratified by the system's predicted verdict, which
would over-weight whatever the system is rare at and produce an accuracy that
could not be generalised. The system's own verdict is **not shown** -- this
project has already been through the version of that mistake where an
adjudicator saw the answers first.

Fill the `verdict` column, put `human` in `labelled_by`, re-run
`scripts/43_evaluate_polarity.py`, and the figures appear on their own. Until
then the report says `"status": "sheet exists but is blank"` rather than
quietly reporting nothing.

---

## Two interfaces, one pipeline

`dashboard/index.html` reads the corpus out; `portal/index.html` takes new
evidence in. Both are static single files, built from a template with their
data injected, and both are scored by the same rule chain -- so a submission
and a scorecard mean the same thing.

```bash
python scripts/45_build_portal.py    # writes portal/index.html
python scripts/41_serve_api.py       # the analyser the portal calls, port 8778
```

The portal shows a contributor what the pipeline read: one row per opinion
unit, the words that triggered each category, and the per-aspect verdict --
alongside the historical baseline for that destination, dated and with `n` on
every row. The corpus ends at a fixed observation date; a submission is the
current layer over it, not a correction to it.

**Three of the seven categories are marked "not checked" in that interface**,
because scenery, price & value and crowding have no human labels behind them.
That marking is read from `reports/accuracy_all_aspects.json` at build time,
not typed into the template -- label those aspects, re-run
`scripts/38_evaluate_against_gold.py` and `scripts/44_accuracy_report.py`,
rebuild, and the marks come off by themselves. See open problem #1.

### Plain words at the edge

The portal is read by someone on holiday, so it carries no research
vocabulary: no *aspect*, *polarity*, *opinion unit* or *F1*. Categories get a
second, friendlier name (`FRIENDLY` in `scripts/45_build_portal.py`), verdicts
read *a problem / something good / just a fact*, and accuracy is a sentence --
"when we say this, we get it right about 8 times in 10".

That sentence is built from **precision**, not F1, because precision is the
number that answers the question it appears to answer: given that we put this
label on a sentence, how often is it right? F1 mixes in recall, which is about
the sentences we missed, and cannot honestly be phrased that way. The
translation happens only at the build step -- nothing in the pipeline is
renamed.

### When the analysis is wrong

Every category on every sentence carries a **Not right?** button, which posts
to `POST /corrections`. Contributors are the people best placed to notice that
"rubbish along the path" was tagged *Roads & Access* -- precision there is
0.588, so roughly two in five of those tags are wrong.

Corrections are stored with `labelled_by='contributor'`, a provenance
`agreement.py` **refuses**. That refusal is the design, not an oversight: a
drive-by correction has no annotation guideline behind it, no second reader,
and nobody to ask what they meant, so it can never become an accuracy or kappa
figure without a deliberate human annotation pass. `GET /corrections` is a
queue for a person to read, and no published number moves because of one.
`tests/test_contributor_separation.py` holds that.

### Storyboard

`POST /stories` and `GET /stories` take longer write-ups and blog links, shown
on the portal's second tab alongside the videos and articles already collected
by `scripts/23_collect.py --what youtube` and `scripts/28_collect_news_targeted.py`.

Storyboard content is **displayed and never counted** -- the existing rule for
collected media (`tests/test_media_separation.py`), which a visitor's blog post
inherits because it is the same kind of object.

### Photos

Place photos come from Wikipedia's API, not Google Places. Places photos need
an API key, and the portal is a static file people copy around, so the key
would travel with it on somebody's billing account -- the same argument that
kept a Google tile layer out of the dashboard's map. Wikipedia needs no key,
allows cross-origin calls, and the images are credited on the page. It is a
weaker match: sometimes there is no photo, and sometimes it is of the town
rather than the site, so the caption says the photo is a guide and not
evidence.

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

**The deployed pipeline uses the rule lexicon for all seven aspects.** That is
not what an earlier version of this section said, and the correction matters
more than the numbers in it, so here is the trace:

`polarity.py` reads `segments_tagged.csv`, which carries only the rule columns
`asp_*`, and writes `segments_scored.csv`. `07_aggregate.py` reads that file,
and `aggregate.long_table` selects an extractor per aspect only if the matching
column is present -- `tAsp_*` for the trained tagger, `sAsp_*` for the safety
model, `uAsp_*` for the union. None of them is. They exist in
`segments_tagged_union.csv`, which nothing downstream reads. So
`aspects_model.ASPECT_EXTRACTOR`, which names `trained` for roads and
facilities and `safety_model` for safety, has no effect on the published
artefact.

Nothing in the published figures is inconsistent -- every number on the
dashboard is rules-throughout, and the whole tree regenerates byte-identically.
What was wrong was the claim, not the arithmetic.

The comparison below is still a real result. It is what each extractor scored
on a purpose-built test set measuring precision *and* recall, and it is why the
lexicon was preferred for four aspects. It is **not** a description of what runs:

| Aspect | Best extractor measured | F1 | Test positives | Deployed |
|---|---|---|---|---|
| Price & Value | rule lexicon | 0.976 | 21 | rule lexicon |
| Scenery | rule lexicon | 0.906 | 25 | rule lexicon |
| Crowding | rule lexicon | 0.903 | 16 | rule lexicon |
| Cleanliness | rule lexicon | 0.901 | 36 | rule lexicon |
| Roads & Access | trained classifier | 0.914 | 33 | **rule lexicon** |
| Facilities | trained classifier | 0.773 | 21 | **rule lexicon** |
| Safety | dedicated classifier | 0.755 | 22 | **rule lexicon** |

Those F1s also come from evaluation sets the assistant labelled itself, and the
human gold set later showed that self-labelled evaluation flattering precisely
the components it existed to justify -- see below. Read the three bold rows as
an untaken option, not as a loss.

Closing the gap means carrying the union and trained columns through the
polarity stage into `segments_scored.csv`, which would move every published
figure and requires the extractor choice to be re-justified against the human
gold set first. Stated here rather than done quietly.

### Measured against human labels

The table above was scored on evaluation sets the assistant labelled itself.
A person outside the pipeline has now labelled 200 rows
(`scripts/38_evaluate_against_gold.py`, Part A only, n=120):

| Aspect | precision | recall | **F1 (human)** | F1 (self-labelled) | change |
|---|---|---|---|---|---|
| Cleanliness | 0.818 | 0.964 | **0.885** | 0.901 | −0.016 |
| Facilities | 0.733 | 0.846 | **0.786** | 0.773 | +0.013 |
| Roads & Access | 0.500 | 0.870 | **0.635** | 0.914 | **−0.279** |
| Safety | 0.394 | 0.867 | **0.542** | 0.755 | **−0.213** |
| | | | **0.712 macro** | | |

**Cleanliness and facilities held. Roads and safety did not** — and those are
the two aspects the trained classifiers were introduced for, so the
self-labelled evaluation was flattering precisely the components it existed to
justify.

The failure is **precision, not recall**. Recall is 0.85–0.96: the pipeline
finds what is there. Safety precision is 0.394, so three in five safety tags
are wrong; roads is 0.500. It over-tags. The annotator hit this by hand within
four rows — "We saw a few monkeys, a deer and a few birds" tagged safety,
"the tuk tuk drivers try to get a commission" tagged roads_access — before any
number said so.

Part B (contested cases, n=80) scores *higher* at 0.808 macro. That is a
sampling artefact: it oversamples rows where the methods disagreed, which are
rows where something fired confidently, so it is denser in true positives.
Headline accuracy is Part A only, per `goldset_focused_sampling.json`.

**The caveat that travels with these numbers:** scored against annotator 1 as
the gold standard. A second annotator labelled the same 200 rows independently
at **kappa 0.746** (substantial), so the scheme behind these labels is
measurably reliable — with `facilities` the weakest at 0.559. See open
problem #1.

---

The headline finding: **for four of seven aspects the lexicon wins outright**,
once its vocabulary gaps are fixed -- and the deployed pipeline in fact runs on
the lexicon for all seven, per the correction above. Those gaps — not the method — were the real
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

1. ~~**No independent human validation.**~~ **Resolved.** Two people
   independently labelled the 200-row focused set, each working from a blank
   sheet with no sight of the other's answers.

   **Cohen's kappa = 0.746 — substantial.**

   | aspect | kappa | exact agreement | |
   |---|---|---|---|
   | Cleanliness | 0.947 | 98.0% | almost perfect |
   | Roads & Access | 0.756 | 90.5% | substantial |
   | Safety | 0.721 | 92.5% | substantial |
   | Facilities | **0.559** | 80.5% | **moderate — the guidelines are soft here** |

   Facilities is the weak spot, and both the second annotator and a separate
   automated pass diverged in the same place: the line between "mentioned"
   (`X`) and "not really about this aspect" (blank). The scheme distinguishes
   complaining from praising cleanly and is vague about bare mentions.

   Accuracy is reported against annotator 1 as the gold standard; kappa is the
   reliability of the scheme that produced it. Two rows were adjudicated by a
   third reader who *had* seen annotator 1's answers — recorded separately in
   `goldset_adjudication.json`, and never used for agreement.

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

   **What it took.** Three separate attempts before a usable second pass
   existed: a reviewer shown annotator 1's answers (adjudication, no kappa),
   an AI assistant (circular — the very problem this open item names), and
   finally a second person working from a blank sheet. Only the third counts,
   and the difference is not a technicality: the first two produce numbers
   that look identical to a real one.

   An AI assistant also labelled the 60-row overlap
   (`reports/automated_second_pass.csv`, mean kappa 0.700 against the human).
   That is kept for error analysis and is **not** reported as agreement: this
   open problem exists *because* the labels came from an assistant, and
   labels from a different assistant reproduce the problem with a statistic
   attached, which reads as validation. The 25 human/automated disagreements
   are listed in `automated_second_pass_disagreements.json` and are a useful
   map of where the guidelines are ambiguous.

   **Outstanding:** one person labelling the blank 60-row overlap sheet,
   about 14 minutes. That is the only thing that produces a reportable kappa.
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
5. **The seven aspects have no category for touts, commissions or pressure
   selling** — found by a human reading the gold set, which is the argument
   for #1 in miniature. 236 segments are about being scammed or overcharged
   ("Watch out for the tourist touts", "the tuk tuk drivers try to get a
   commission from every place they take you"). Most are absorbed by
   `price_value` because they mention money, but that aspect was defined as
   *entrance fees, parking charges, value for money* — it catches them by
   accident. Around 30 carry no aspect word at all ("Absolute scam.") and are
   invisible to every scorecard. The tuk-tuk example is tagged `roads_access`,
   which is defensible — a tuk tuk is transport — and is the wrong reading,
   because the complaint is about money.

   Not fixed here. An eighth aspect means a new lexicon, a retrained
   classifier and a redone evaluation. Stated as a scope limit instead: this
   project measures complaints about the PLACE, not about the people trading
   around it.

6. **Reddit needs an app registration**; the public JSON endpoint returns 403.
7. **Three districts have no data**: Monaragala, Puttalam, the Vanni.

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
| **overall complaint rate** | **-0.440** | 225 | <0.001 |
| Scenery | -0.315 | 220 | <0.001 |
| Crowding & Noise | -0.309 | 123 | 0.0005 |
| Cleanliness | -0.281 | 95 | 0.006 |
| Facilities | -0.197 | 102 | 0.047 |
| Price & Value | -0.123 | 89 | 0.25 *(ns)* |
| Roads & Access | -0.071 | 127 | 0.43 *(ns)* |
| **Safety** | **+0.091** | 61 | 0.49 *(ns)* |

These are computed over the destination-aspect cells the dashboard actually
publishes, so they moved when the evidence threshold was raised from 5 opinions
to 10 (see *Evidence thresholds*, below). Every n is smaller and the overall
correlation is slightly **stronger** -- dropping the cells that were measured to
be unreliable removed noise, not signal, which is a small piece of corroboration
for the threshold in its own right.

Two things worth reading carefully.

**The overall rate holds up.** Destinations this pipeline calls heavily
complained-about do rate lower with the travelling public, at rho = -0.44
across 225 places. That is not proof any individual label is right, but a null
or positive correlation would have been a serious warning, and it is not what
came back.

**Safety shows no detectable relationship with star ratings — and that is the
finding, not a failure.** This project already documented that **55.3% of
safety complaints sit inside reviews a star-trained model reads as positive**:
a visitor warns that the current is dangerous and still gives five stars.
If that is true, a star rating *cannot* track safety complaints, and this
independent measurement is exactly what you would predict. The same ordering
appears in both analyses — cleanliness 0.8%, roads 21.2%, safety 55.3%
contamination, against correlations of -0.28, -0.07 and +0.09. Safety's sign is
positive here where it was slightly negative before the threshold change; both
values sit well inside the noise around zero at p≈0.5, which is the claim being
made. A correlation that changes sign under a routine change of scope is not a
correlation, and that is the finding.

So the weakest correlation in the table is the strongest argument in the
project: **for safety, the star rating is measuring something else, which is
precisely why aspect-based complaint mining is worth doing.**

Read the other direction, though, safety is also the aspect most dependent on
a hand-written rule (open problem #2) and the one with the fewest destinations
here (n=106). Both readings are live until the human gold set exists.

**Coverage:** our corpus size per destination correlates with the public
rating count at **rho = 0.62** — the reviews we hold track how busy a place
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
scripts/            numbered entry points; 49 builds all, 50 launches
reports/            evaluation sets, scores, gold sheets, annotation guidelines
dashboard/          template.html (source) + index.html (built)
portal/             template.html (source) + index.html (built)
release/            citable bundle + DATASHEET.md + SOURCES.md
data/processed/     working files (mostly gitignored, regenerable)
tests/              separation and provenance guarantees
```

The numbered scripts are the record of how the project was built and every one
still runs on its own. `49_build_all.py` is the subset that has to run, in the
order it has to run in.

Every threshold and routing decision is documented **in the code, beside the
thing it controls**, with the measurement that justified it. If a number looks
arbitrary, the comment above it explains where it came from — or says plainly
that it was assumed and needs validating.
