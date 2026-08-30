# Ceylon Foods — Sri Lankan Food AI

Semantic search and recommendation over 155 Sri Lankan dishes, with health-aware
and fully explainable ranking, LKR price estimates, and nearby places to eat.

- **Backend** — FastAPI. A seven-stage retrieval pipeline: query understanding,
  hard constraint filtering, hybrid dense + sparse retrieval, reciprocal rank
  fusion, cross-encoder reranking, additive signal scoring, MMR diversification.
- **Frontend** — React 18 + Vite, slate-navy and violet theme, no CSS framework.
  Every dish card carries a photo, served as a static asset and matched to the
  dish by name; see [Dish photos](#dish-photos).
- **Prices and places** — a per-dish LKR range scaled by venue tier, and venue
  lookup through OpenStreetMap Overpass or Google Places. See
  [Prices and places](#prices-and-places) for what is measured and what is
  estimated.

---

## Quick start

Two terminals.

```bash
# 1 — API  (http://localhost:8000, docs at /docs)
cd backend
python -m venv .venv && .venv\Scripts\activate.bat
pip install -r requirements.txt
uvicorn main:app --reload
```

```bash
# 2 — client  (http://localhost:5173)
cd frontend
npm install
npm run dev
```

## How to run backend
```bash
# 1 — API  (http://localhost:8000, docs at /docs)
cd backend
.venv\Scripts\activate
uvicorn main:app --reload
```

## How to run frontend
```bash
# 2 — client  (http://localhost:5173)
cd frontend
npm run dev
```


The bi-encoder (`BAAI/bge-small-en-v1.5`, ~130 MB) and cross-encoder
(`BAAI/bge-reranker-base`, ~1.1 GB) download from Hugging Face on first run and
are cached by `huggingface_hub`. Corpus embeddings are then cached to
`backend/.cache/`, so later restarts skip encoding entirely.

**The API starts and serves results even if those models are unavailable.** See
[Graceful degradation](#graceful-degradation).

### Tests

```bash
cd backend && python -m unittest discover tests -v   # 421 tests
cd frontend && npm run verify                        # build-free static checks
```

Neither command needs network access, an API key, or the ML stack: the venue
providers are exercised against captured payloads, and `tests/test_places.py`
replaces `urlopen` with a function that fails loudly, so a test that starts
making live calls fails rather than quietly depending on someone's rate limit.

---

## What changed, and why

The original implementation was a 609-line `backend/main.py` and a 433-line
`frontend/index.html` that loaded React from a CDN and transpiled JSX in the
browser. It worked, but the ranking logic was a single function containing a
hand-tuned chain of keyword tests, and the health rules were implemented twice.

### Correctness bugs found and fixed

Each of these is pinned by a test named `test_regression_*`, except items 23–25,
which were found by auditing the README's own claims about the client against the
code. Item 23 is covered by the render harness described under
[Testing](#testing); 24 and 25 are covered in `test_places.py`.

| # | Bug | Effect |
|---|-----|--------|
| 1 | `alpha * sem_map.get(i, 0.0)` in fusion | Candidates found by BM25 but outside the dense top-40 got a dense score of **0.0**, silently discarding 65% of their score. A perfect lexical match could not outrank a mediocre semantic one. |
| 2 | Substring matching without word boundaries | `'tea' in query` fired on "ins**tea**d" and "s**tea**med"; `'sweet' in query` forced dessert-only filtering for "**sweet** potato". |
| 3 | **No negation handling at all** | `"not vegetarian"` matched `'vegetarian'` and filtered *to* vegetarian. `"I don't want seafood"` returned **only** seafood. Results were inverted. |
| 4 | `score = proba.max()` in `/recommend` | Returns the probability of the single most likely dish — the same value for every row, never referencing the row's own class. The model contributed nothing to the ordering. |
| 5 | `predict_proba` called once per dish | 155 model invocations per request, where the features admit exactly one distinct row. Now 1. |
| 6 | Missing BGE query instruction prefix | BGE is asymmetric and its model card requires `"Represent this sentence for searching relevant passages: "` on queries. Free accuracy, left unclaimed. |
| 7 | `'Very High'` spice branches | Dead code — the dataset only contains `None/Low/Medium/High`. |
| 8 | Corpus re-encoded on every boot; `@app.on_event` | Slow cold start, deprecated API. |
| 9 | Multiplicative penalties | `0.3 × 0.15 × 0.1 = 0.0045` — three mild signals caused a 200× cut, and no single factor was recoverable from the final score. |
| 10 | `'egg' in 'eggplant curry'` | **Eggplant Curry** and **Wambatu Moju** were flagged as unsafe for egg allergies. |
| 11 | `'milk'` matched "coconut milk" | Coconut curries flagged as containing dairy — a false lactose-intolerance warning. |
| 12 | `'beer' in 'ginger beer'` | Sri Lankan ginger beer (a soft drink) flagged as alcohol for gout. |
| 13 | Health rules duplicated in backend **and** frontend | Two copies that had already drifted, so the UI and API could disagree about whether a dish was safe. |
| 14 | Negation window over-captured | A fixed 4-token window meant `"not vegetarian dinner"` also negated **dinner**, discarding the meal time. |
| 15 | `'free'` treated as a prefix cue | `"gluten free breakfast"` excluded *breakfast*. |
| 16 | Custards untagged | **Caramel Pudding** — an egg-and-dairy custard — carried neither tag, because its description never says "egg" or "milk". |
| 17 | Per-request state on the service object | `self._fused_scores` raced between concurrent requests, since FastAPI dispatches sync handlers onto a threadpool. |
| 18 | Spice and diet as soft penalties | Bi-encoders embed "not vegetarian" *close to* "vegetarian", so the retriever ranks vegetarian dishes top for that query and a −0.30 penalty cannot close a +0.60 relevance gap. Both are now hard filters. |
| 19 | Thousands separator lost to tokenisation | `"under 1,000 rupees"` became `["1", "000"]` and read as a **Rs 1** budget — a 1000× error that quietly returned only the cheapest dishes. |
| 20 | Adjacent digit groups rejoined | The first fix for 19 merged any two adjacent 3-digit groups, so `"top 10 500"` became Rs 10,500 and `"300-800 rupees"` became Rs 300,800 — then exceeded the plausible maximum and was dropped, losing the budget entirely. Separators and hyphenated ranges are now handled on the raw text. |
| 21 | Currency word matched across a number | `_currency_near` looked two tokens ahead unconditionally, so the "rupees" in `"top 10 500 rupees"` attached to the **10**; the most restrictive bound wins, so the wrong reading survived. |
| 22 | `"budget 1500"` parsed to nothing | "budget" and "spend" were filler rather than cues, and an amount with neither a comparator nor a currency word is discarded. |
| 23 | The parsed budget never reached the client | The server worded the amount and returned it as `understanding.budget` — with a comment saying the UI would show it — and `QueryInsights` never read the key. So the one signal that reweights every result was the only one with nothing on screen, which is exactly backwards: the invisible constraint is the one that most needs to be visible. |
| 24 | `/venues/nearby` shipped no disclaimer | `find()` carried the "no provider publishes menus" caveat and `nearby()` carried neither it nor the confidence legend, so whether a user saw the honesty note depended on which endpoint the client called. Both now return the same keys, worded for what each can actually be wrong about. |
| 25 | Dish-free venues carried an empty reason | `nearby()` set `reason=""` while every venue kept the dataclass default of `category` confidence, so the client rendered a bare "category" badge with no tooltip — a verdict about a dish nobody had named. |

Items 10–12 and 16 matter more than their size suggests: a false allergy warning
teaches users to distrust every other warning. Items 19–22 are the same shape in
a different layer: a misread budget silently reshapes the entire result page, and
nothing on screen says so. Items 23–25 are a third variant, and the most
instructive: in each case the *server* was right and the caveat or the constraint
simply never reached the screen. They were found by taking each claim this README
makes about the client and checking it against the code, which is a review pass
worth repeating — documentation that describes intent rather than behaviour is how
all three survived.

### Data-quality note

The curated prose and the structured columns disagree for some dishes.
**Chicken Curry** and **Crab Curry** are both described as "High spice" but are
recorded as `Medium` in the CSV. All ranking and health logic keys off the
structured column, so the prose disagreement stays inert. Pinned by
`test_structured_column_wins_over_prose`.

---

## Pipeline

```
query
  │
  ├─ 0  query understanding        nlu.py        typo correction, negation-scoped
  │                                              constraint extraction
  ├─ 1  hard constraint filter     ranking.py    allergens, diet, spice band, category
  │
  ├─ 2  candidate generation       dense.py      BGE bi-encoder  (+ FAISS ≥ 5k docs)
  │                                lexical.py    BM25 Okapi, inverted index
  │                                lexical.py    fuzzy dish-name matcher
  ├─ 3  rank fusion                fusion.py     Reciprocal Rank Fusion
  ├─ 4  cross-encoder rerank       reranker.py   bge-reranker-base   (optional)
  ├─ 5  additive signal scoring    ranking.py    explainable, bounded
  ├─ 6  MMR diversification        fusion.py     relevance ⇄ variety
  └─ 7  response assembly          search.py     + understanding / filters / pipeline
```

### 0 — Query understanding

`nlu.py` is stdlib-only and turns free text into a structured `Constraints`
object. This is the layer the original design lacked entirely.

Negation scope is resolved **per matched phrase**, not over a token window: from
each facet phrase, look backwards past up to three filler tokens and decide from
the first meaningful token found — a cue negates, a conjunction inherits the
previous polarity (`"no eggs or dairy"` excludes both), and a scope breaker stops
it (`"not spicy but seafood"` leaves seafood positive).

```
"I don't want seafood"           → exclude seafood          (hard filter)
"gluten free breakfast"          → exclude gluten, meal=Breakfast
"not vegetarian dinner"          → diet=nonveg, meal=Dinner
"anything but seafood"           → exclude seafood
"mild curry for tourists"        → spice ≤ Low, category=Curries, +beginner_friendly
"watalapan"                      → typo → Watalappan, exact-name lookup
"tea time snacks"                → +tea_time  (not the Drinks category)
```

Contractions are expanded **before** punctuation is stripped — otherwise
`"don't want seafood"` becomes `"don t want seafood"`, the cue is destroyed, and
the query silently inverts.

### 1 — Hard vs soft constraints

Hard constraints remove documents; soft ones adjust scores.

| Constraint | Enforcement | Reasoning |
|---|---|---|
| Allergen exclusion | **Hard, never relaxed** | Safety, not relevance. Returning nothing is correct when everything available is unsafe. |
| Diet (both directions) | **Hard**, relaxable | Soft penalties lose to relevance — see bug 18. |
| Spice band | **Hard**, relaxable | Same, and it is the attribute users state most firmly. |
| Single decisive category | **Hard**, relaxable | "show me drinks" should mean drinks. |
| Meal time, price, tags, preferences | Soft | Genuine preferences; ranking is the right tool. |

Relaxable filters are guarded by `MIN_SURVIVORS = 3`: if a filter would leave
fewer than three dishes it is skipped, reported in `filters.relaxed`, and the
additive signal handles ordering instead. A narrow query degrades to ranking
rather than to an empty page.

### 2 — Retrieval

Two documents are built per dish, for two different consumers:

- `dense_text` — fluent prose for the bi-encoder. Sentence encoders are trained
  on natural language, so a readable sentence embeds better than a term bag. The
  original builder emitted keyword soup (`"... Meal time: Any. Spice: None. mild
  low spice not spicy gentle ..."`) and fed it straight to the encoder.
- `sparse_tokens` — a weighted bag for BM25, with the dish name repeated 3× and
  tags 2×. Term repetition is meaningless to an encoder but is exactly how you
  express field weighting to a term-frequency model.

Symmetrically, the **dense side receives the clean query** while the **sparse side
receives the expanded token bag** with negated spans removed. The original
appended synonyms to one string and gave it to both; keyword stuffing degrades
sentence embeddings, and leaving `seafood` in the BM25 bag for "no seafood"
actively retrieves the excluded dishes.

BM25 is implemented in-process (`lexical.py`) rather than via `rank-bm25`: at 155
documents the dependency bought nothing, `rank_bm25` scores the entire corpus on
every query where an inverted index touches only matching documents, and owning
it makes sparse retrieval unit-testable without the ML stack.

FAISS is engaged only above 5,000 documents. Below that, exact NumPy search is
faster once index construction and call overhead are counted. Both paths are
exact — `IndexFlatIP` on L2-normalised vectors and `embeddings @ query` compute
the same cosine similarities — so the switch cannot change results.

### 3 — Reciprocal Rank Fusion

RRF consumes only *ranks*, so the retrievers' incomparable score scales (cosine
in [−1, 1] versus unbounded BM25) never have to be reconciled, and a document
missing from one list contributes nothing from it instead of a zero that drags a
weighted mean down. That is bug 1, structurally prevented.

### 4 — Cross-encoder reranking

The largest single accuracy gain, and absent from the original. A bi-encoder
embeds query and document independently, so the two never interact and the model
cannot tell that "mild" attaches to "curry" rather than to something else in the
document. A cross-encoder concatenates the pair and runs attention across both —
affordable precisely because stages 1–3 reduced the candidate set first.

### 5 — Additive scoring

```
score = relevance + Σ signalᵢ
```

Every signal is a bounded additive term with a name and a human-readable reason,
so a result can explain itself:

```json
{
  "name": "Dhal Curry",
  "score": 1.084,
  "explanation": {
    "relevance": 0.664,
    "rerank_score": 0.712,
    "retrievers": ["dense", "sparse"],
    "signals": [
      { "name": "relevance", "contribution": 0.664, "detail": "semantic + lexical match" },
      { "name": "diet",      "contribution": 0.30,  "detail": "vegetarian" },
      { "name": "spice",     "contribution": 0.26,  "detail": "Low spice fits" },
      { "name": "meal_time", "contribution": 0.054, "detail": "suitable any time" },
      { "name": "health_caution", "contribution": -0.18, "detail": "use caution with your health profile" }
    ]
  }
}
```

The contributions sum to `score` exactly, which the UI's "Why?" panel renders as
signed bars. This view is only possible because scoring is additive — there was
nothing to decompose before.

One deliberate subtlety: 101 of 155 dishes are labelled `meal_time = "Any"`, so an
"Any" dish matching "breakfast" earns only 30% of the meal-time bonus. Without
that discount the generic majority swamps the six genuine breakfast dishes.

### 6 — MMR diversification

Standard MMR over the embeddings, plus a category-repeat penalty. Embedding
similarity alone still returns six kottu variants, because they genuinely are all
relevant and only moderately similar as vectors. Note that MMR output is
intentionally **not** monotonic in score: position 2 is the best *marginal*
addition, not the second-highest scorer.

---

## Graceful degradation

Everything except the three model artifacts is pure Python, so the API stays up
and useful when they are missing. `GET /health` reports which stages are live, and
the UI surfaces a banner — a silent quality downgrade is worse than a visible one.

| Missing | Behaviour |
|---|---|
| Embedding model | Lexical-only mode: BM25 + fuzzy names. Constraints still fully enforced. |
| Cross-encoder | First-stage fused ranking. `pipeline.reranked = false`. |
| `sri_lankan_food_model.pkl` | `/recommend` falls back to deterministic preference scoring. The original swallowed prediction failures into `score = 0.0`, producing an arbitrary order with no indication anything was wrong. |
| FAISS | Exact NumPy search (the default below 5k docs anyway). |
| Venue provider (timeout, quota, no key, no network) | 28 bundled landmark venues, flagged `source: "seed"` and `approximate: true`. An empty list would read as "nothing near you", which is a different and wrong answer. Failures are not cached, so a transient timeout does not pin a degraded result for the whole TTL. |

---

## API

Interactive docs at `/docs`.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/search` | Main pipeline. Returns results + `understanding` + `filters` + `pipeline`. |
| `GET` | `/search?q=` | Same, for debugging and shareable links. |
| `GET` | `/autocomplete?q=` | Dish-name typeahead, fuzzy fallback for typos. |
| `POST` | `/similar` · `GET /similar/{name}` | Nearest neighbours in embedding space. |
| `POST` | `/recommend` | Structured preferences → XGBoost blended with rules. |
| `GET` | `/conditions` | Health-condition catalogue. **The client renders this rather than hardcoding it.** |
| `POST` | `/health-check` | Warnings for named dishes against conditions. |
| `GET` | `/facets` | Facet values with counts. |
| `GET` | `/dishes` · `/dishes/{name}` | Browse the catalogue. |
| `GET` | `/prices` | Whole-table view: every estimate plus provenance, `unpriced`, and `band_mismatches`. An operator/diagnostic surface — the cards do not need it, since every dish payload already embeds its own price. |
| `GET` | `/prices/{name}` | One dish, including the per-venue-tier breakdown. |
| `GET` | `/cities` | City centroids for the picker shown when geolocation is denied. |
| `POST` | `/venues/nearby` | Food venues near a point, independent of any dish. |
| `POST` | `/dishes/{name}/venues` | Where to eat one dish, nearest first, with the dish's price attached. |
| `GET` | `/health` | Liveness plus per-stage availability. |
| `GET` | `/config` | Effective ranking configuration. The Google key is redacted to `"***set***"`. |
| `GET` | `/options` | *Deprecated* — kept for the original client. |

```bash
curl -s localhost:8000/search -H 'Content-Type: application/json' -d '{
  "query": "mild vegetarian breakfast without coconut",
  "top_k": 5,
  "health_conditions": ["diabetes"],
  "explain": true
}'
```

`search` accepts `strict_allergens` (remove unsafe dishes rather than flagging
them), `explain`, `rerank` and `diversify`.

The two venue endpoints are `POST` despite being reads. The body carries the
user's coordinates, and a live position in a URL is written into access logs,
`Referer` headers and browser history; the responses are also not cacheable by a
shared cache for the same reason. Either a position or a city name is accepted:

```bash
curl -s localhost:8000/dishes/Chicken%20Kottu/venues \
  -H 'Content-Type: application/json' \
  -d '{"latitude": 6.927, "longitude": 79.861, "radius_km": 3, "limit": 8}'

curl -s localhost:8000/venues/nearby -H 'Content-Type: application/json' \
  -d '{"city": "Kandy"}'
```

### Health engine

Conditions are declarative maps from a nutrition/ingredient **tag** to a severity
and a message. One tagging pass over `name + description` feeds facet filtering,
ranking signals and health warnings alike — one source of truth, replacing three
drifting copies of the same keyword vocabulary.

All matching is word-boundary anchored, and tags carry *negative* keywords,
because a keyword ontology otherwise produces confident false positives:

```
"creamy coconut milk potato curry"  →  not dairy   (plant milk)
"boiled sweet potatoes"             →  not sugary
"sweet spicy stir-fried chicken"    →  not a dessert
"ginger beer"                       →  not alcohol
"custard"                           →  egg
```

`Watalappan` is a *coconut* custard, so dairy is matched on explicit dish names
rather than inferred from "custard".

---

## Prices and places

Both of these features answer questions the dataset cannot: what a dish costs in
rupees, and where to eat it. Neither answer is measured, so the design goal
throughout is that the response says how good it is.

### The price table

`app/data/prices.py` holds a `low, typical, high, unit, confidence` tuple for all
155 dishes in LKR, dated by a single `PRICE_AS_OF` (`2025-05-01`). Coverage is
all-or-nothing on purpose and pinned by a test: a price on some cards and not
others reads as "this one is free" rather than "we do not know".

Every endpoint that returns a dish embeds that dish's price, through the single
`Dish.public_dict(price)` shape — which is what stops `/search`, `/dishes`,
`/similar` and `/recommend` from drifting into four different price shapes, and
means no card waits on a second request or renders before its own price arrives.
The price is a parameter rather than a `Dish` field because it depends on the
loaded table, the inflation multiplier and today's date, none of which the corpus
knows about.

The unit is never blank, and that is a correctness property rather than a
formatting one. Rs 40 for Plain Hoppers is *per hopper*; Rs 700 for Rice and
Curry is *per plate*. A figure rendered without its unit is not imprecise, it is
false — so `test_unit_is_never_empty` guards a wrong-by-1000 class of bug.

Every payload carries `estimated: true`, `confidence` (`high` for 94 dishes,
`medium` for 53, `low` for 8), `as_of`, `age_days` and `stale`. The table goes
stale after a year (`FOODAI_PRICE_STALE_DAYS`), and `stale` is a read-only
property: a settable flag would let a caller mark a two-year-old table fresh,
which is precisely the failure it exists to prevent.

Figures are rounded to a step that follows their magnitude — 5 below 100, then
10, 50, 100 — because Rs 517.40 implies a precision that is not there. Rounding
is applied *after* ordering is checked, since rounding a tight range can invert
it and print "Rs 200 - 190".

### Prices versus the dataset's own column

The CSV has a `price_range` column of `Low`/`Medium`/`High`, and that column is
both a feature of the pickled XGBoost model and an ordinal in the NLU layer, so
it cannot be repurposed or overwritten. The numeric table therefore derives its
own band (≤ Rs 500 low, ≤ Rs 1,200 medium, above that high) and the two are
cross-checked on every request. Disagreements are **reported, never reconciled**:
`/prices` returns `band_mismatches`, and `test_derived_bands_agree_with_the_dataset`
pins the mismatch set exactly — currently one dish, Crab Curry — so new drift
fails the suite instead of passing silently.

`FOODAI_PRICE_INFLATION` re-bases every figure without touching any band, since a
uniform re-basing is not a statement about relative cost and must not reshuffle
dishes between Low, Medium and High.

### Venue tiers

One number for "how much is kottu" is wrong at both ends of the market, so the
typical price is scaled per venue class and each venue is priced for its own tier:

| Tier | ×    | Chicken Kottu |
|---|---|---|
| street  | 0.72 | Rs 550 – 900 |
| bakery  | 0.85 | Rs 650 – 1,100 |
| canteen | 0.88 | Rs 700 – 1,150 |
| casual  | 1.00 | Rs 800 – 1,300 |
| cafe    | 1.25 | Rs 950 – 1,600 |
| tourist | 1.65 | Rs 1,300 – 2,100 |
| hotel   | 2.40 | Rs 1,850 – 3,100 |

The tier is inferred from provider tags — `tourism=hotel` or a `stars` tag, an
international cuisine, `fast_food`, `bakery`, Google's `priceLevel` — and this is
arithmetic on one baseline, not observed per venue. `/prices/{name}` says so in
the payload, because a figure labelled "hotel" otherwise looks researched.

### Budget queries

The NLU layer parses amounts into `max_price_lkr` / `min_price_lkr`, kept separate
from the `price_floor` / `price_ceiling` ordinals for the reason above. It handles
comparators ("under 500", "up to Rs 500", "500 or less"), floors, ranges
("between 300 and 800", "300-800 rupees"), approximations ("around 700" → ±25%),
glued units ("500lkr", "rs500"), implied ceilings ("budget 1500", "spend 800"),
and negation — "no more than 500" is a ceiling, though "more" is a *minimum* cue
and read literally it would return exactly the dishes the user was avoiding.

Amounts are echoed back in words (`understanding.budget: ["up to Rs 1,500"]`) and
rendered as a chip in the insights panel's *Understood* row, beside the facets the
query stated. The server does the wording and the client repeats it verbatim, so
the phrasing the parser committed to is the phrasing on screen. This matters more
than the other chips: the bound is a scaled soft signal (`FOODAI_W_BUDGET`) rather
than a filter, so it narrows the ranking without ever emptying the page — a dish
Rs 50 over is not treated like one Rs 3,000 over — which also means a misread
amount reshapes the whole result page with nothing else on it to say so. It went
unrendered for exactly that reason (bug 23).

Quantities are not budgets. "less than 3 chillies" and "top 5 spicy dishes" parse
to nothing, an amount needs either a comparator or a currency word, and anything
outside Rs 10–200,000 is a year or a phone number rather than a dish price.

### Finding venues

`FOODAI_PLACES_PROVIDER` selects `overpass` (default, keyless), `google`, `seed`
or `none`. Each dish maps to a venue profile — selectors to query, plausible
cuisines, and name keywords including spelling variants (kottu, kotthu, koththu,
kothu) — and every result is labelled with the evidence behind it:

| Confidence | Evidence |
|---|---|
| `named` | the venue's name, or a curated note, mentions the dish |
| `cuisine` | its cuisine tags match the dish's style |
| `category` | this kind of place usually sells it |

Confidence outranks distance in the sort order, then distance, then name for
determinism. The feature answers "where can I eat *this*", not "where can I eat":
a place listed as serving the dish 2 km away beats a generic restaurant 200 m away
that may not sell it at all. Keyword matching is word-boundary anchored, so
"Steakhouse" is not a tea shop. Accompaniments like Lunumiris return a note
instead of a venue list, since a list of restaurants implies you can walk in and
order a bowl of it.

No POI provider publishes menus. Both venue endpoints therefore carry a
`disclaimer` and a `confidence_legend`, and the client renders the disclaimer
verbatim rather than composing its own wording. `/venues/nearby` originally
carried neither, which made the caveat a property of the endpoint you happened to
call rather than of the data; it now returns the same keys as `/dishes/{name}/venues`
so one component can render either payload. The two disclaimers are worded
differently on purpose — a dish search can be wrong about the dish, a dish-free
search can only be wrong about the venue — and for the same reason a nearby result
says "no dish was specified" instead of borrowing one of the four dish-evidence
reasons.

### Location handling

Coordinates are coarsened to three decimals (~110 m) on both the client and the
server — enough to find a restaurant, not enough to identify a doorstep — and the
coarsened point is what reaches the provider and the cache, since rounding after
the upstream call protects nobody. Coordinates are never written to logs, which
`test_coordinates_are_never_logged` asserts against the actual log output. When
permission is denied the client falls back to the `/cities` picker (35 city
centroids); an unknown city name resolves by exact match or unique prefix and
otherwise fails, because sending someone to the wrong end of the island is worse
than asking again.

Lookups are cached with a TTL, keyed on the provider, the coarsened point and the
*selector set* rather than the dish, so all 22 Short Eats share one upstream call
and two users on the same street share a request. Seed results link to a map
*search by name* rather than a pin, because a wrong pin is worse than one extra
tap.

**The Google Places key is server-side only.** It lives in
`FOODAI_GOOGLE_PLACES_KEY`, is redacted in `/config`, and must never be placed in
a `VITE_*` variable — Vite inlines those into the published browser bundle.

---

## Configuration

Every ranking weight and stage parameter is an environment variable; see
`backend/app/config.py`, or `GET /config` for effective values.

```bash
FOODAI_RERANK_ENABLED=false     # skip the cross-encoder
FOODAI_MMR_LAMBDA=0.95          # 1.0 = pure relevance, 0.0 = pure diversity
FOODAI_W_HEALTH_DANGER=-0.8     # harsher penalty for unsafe dishes
FOODAI_W_BUDGET=0.28            # weight of a stated rupee budget
FOODAI_RRF_K=60                 # RRF smoothing constant
FOODAI_EMBEDDING_CACHE=false    # always re-encode
```

Prices:

```bash
FOODAI_PRICING_ENABLED=true
FOODAI_PRICE_TABLE=prices.csv   # override the estimates: name,low,typical,high[,unit,confidence]
FOODAI_PRICE_AS_OF=2026-01-15   # date the override was collected
FOODAI_PRICE_INFLATION=1.25     # re-base every figure; bands unchanged
FOODAI_PRICE_STALE_DAYS=365     # 0 disables the staleness badge
FOODAI_PRICE_CURRENCY=LKR
FOODAI_PRICE_SYMBOL=Rs
```

A malformed row in the override is skipped rather than fatal — one bad line must
not take the API down at boot — and rows without a `unit` default to `portion`.

Places:

```bash
FOODAI_PLACES_ENABLED=true
FOODAI_PLACES_PROVIDER=overpass       # overpass | google | seed | none
FOODAI_OVERPASS_URL=https://overpass-api.de/api/interpreter
FOODAI_GOOGLE_PLACES_KEY=...          # server-side only; never a VITE_ variable
FOODAI_GOOGLE_PLACES_URL=https://places.googleapis.com/v1/places:searchNearby
FOODAI_PLACES_TIMEOUT=8
FOODAI_PLACES_RADIUS_KM=3             # default when the client sends none
FOODAI_PLACES_MAX_RADIUS_KM=25        # ceiling on what a client may ask for
FOODAI_PLACES_MAX_RESULTS=12
FOODAI_PLACES_CACHE_TTL=900
FOODAI_PLACES_CACHE_SIZE=256
FOODAI_PLACES_COORD_PRECISION=3       # decimals kept; 3 ≈ 110 m
FOODAI_PLACES_USER_AGENT='YourApp/1.0 (+https://your.site)'
FOODAI_PLACES_FALLBACK_SEED=true      # false = return empty + degraded instead
```

Set a real `FOODAI_PLACES_USER_AGENT` before pointing this at the public Overpass
instance: its usage policy requires an identifiable agent, and the default names
this project.

Frontend: `VITE_API_URL` (see `frontend/.env.example`).

---

## Layout

```
backend/
  main.py                 # shim so `uvicorn main:app` still works
  requirements.txt
  app/
    config.py             # all tunables, env-overridable
    corpus.py             # loading, tagging, dense/sparse document building
    nlu.py                # query understanding            (stdlib only)
    lexical.py            # BM25 + fuzzy names              (stdlib only)
    dense.py              # bi-encoder, embedding cache, FAISS/NumPy
    reranker.py           # cross-encoder, optional
    fusion.py             # RRF, normalisation, MMR         (stdlib only)
    ranking.py            # hard filters + additive scoring (stdlib only)
    search.py             # pipeline orchestrator
    recommend.py          # XGBoost + rule blend
    health.py             # conditions and warnings         (stdlib only)
    pricing.py            # LKR bands, tiers, staleness     (stdlib only)
    places.py             # venue providers, cache, finder  (stdlib only)
    schemas.py            # request validation
    main.py               # FastAPI app and routes
    data/
      descriptions.py     # 155 curated descriptions
      taxonomy.py         # facet lexicon + tag ontology
      prices.py           # 155 price estimates + tier multipliers
      venue_profiles.py   # dish -> selectors, cuisines, name keywords
      venues_seed.py      # 35 city centroids + 28 landmark venues
  tests/                  # 421 tests, stdlib unittest

frontend/
  public/
    dishes/               # 155 dish photos, one per dish, named by slug
  src/
    api/client.js
    lib/dishImage.js      # dish name -> photo path (the only copy of the rule)
    hooks/                # useDebounce, useGeolocation, useHealthProfile, useResource
    components/
      layout/  search/  recommend/  health/  food/  location/  ui/
    styles/               # theme.css (tokens) + components.css
  scripts/
    verify.mjs            # build-free static checks
    dishNames.mjs         # the dish list, read from the backend's CSV
    import-dish-images.mjs  # copies photos into public/dishes under their slugs
```

### Frontend notes

Dependencies are `react`, `react-dom`, `vite`, `@vitejs/plugin-react` — nothing
else. No CSS framework: the styling surface is small and fully known, and this
leaves nothing extra to version-manage.

The theme is a slate-navy neutral ramp with violet as the interactive accent, the
same palette the SafeTravel LK design system uses, so the two read as one product.
The rule that survived the recolour is the one that matters: violet marks *the
interface* — filled buttons, focus rings, the active tab, a link on hover — and
never a health signal, so red, amber and green still carry severity alone. A red
border on a card is a statement about the food and nothing else. Two values depart
from the source tokens on purpose, both for contrast: filled controls use
violet-600 rather than violet-500 (white on violet-500 measures 4.2:1, just under
the 4.5:1 that 13px text needs; violet-600 is 5.7:1), and the three semantic
colours are one step lighter than the source's, because here they are read as small
text on a dark surface rather than as a marker dot. Emoji were replaced with inline
SVG: they render differently per platform and cannot inherit colour, and the state
being communicated is sometimes "do not eat this".

The UI deliberately exposes the pipeline rather than hiding it: detected
constraints, corrected typos, which filters became hard, which stages ran, and
per-signal score breakdowns.

Clicking a card opens a dialog with that dish's price and its nearby places. This
replaced a "Where to eat" button in the card footer that expanded the venue list
in place: eight rows of name, distance, confidence and three links, rendered
inside a 300px grid column, wrapped into a panel twice the height of the card it
hung off and pushed every card below it down the page while you read. The dialog
gets the width the list needs and leaves the grid still.

Two details of that are load-bearing rather than cosmetic. The dialog is mounted
by `FoodGrid`, not by `FoodCard`, because `.card:hover` and `.anim-rise` both set a
`transform` and a transformed element becomes the containing block for its
`position: fixed` descendants — inside a card, the dialog would be positioned
against the card, and only while hovered. And the trigger is a real `<button>`
wrapping the card title, not a click handler on the `<article>`: the whole card
surface is a mouse shortcut, but an `<article>` with an `onClick` is unreachable by
keyboard, and a `<button>` wrapped around a photo, four chips and two other buttons
is invalid HTML. What is *not* claimed: the dialog closes on Escape and moves focus
to its close button, but it is not a focus trap — Tab from the last link walks out
into the page behind.

"Why?" is the only action left in the footer, and it appears only when the server
sent an explanation. A third card action, "Similar", was removed earlier. The
drawer it opened — nearest neighbours in the embedding space — still exists in
`components/food/SimilarDrawer.jsx`, and so does `POST /similar` behind it; nothing
mounts the drawer now, and both the component and its API helper say so at the top
rather than sitting there looking live. Re-attaching it is one piece of state in
`App.jsx` and one call site.

### Dish photos

Every dish has a photo, and the API has no image field. The client derives the
path from the dish name — `dishSlug('Kiri Toffee (Milk Toffee)')` gives
`dishes/kiri-toffee-milk-toffee.jpg` — because the name is already the join key
for the CSV, the descriptions, the price table and the venue profiles. Nothing new
has to be kept in sync on the server, and no card waits on a second request to
learn where its picture lives.

Deriving the path costs something, though: it is a claim the server cannot check.
`npm run verify` checks it instead, in **both** directions, using the same
`dishSlug` the app imports rather than a second copy of the rule. A dish with no
photo fails the build, and so does a photo with no dish — the second being the one
that hides, because it means a dish was renamed in the CSV and the stale file is
still being shipped while the new name renders a hole. Photos are imported by
`node scripts/import-dish-images.mjs <source-dir>`, which matches on the slug (so
`Mutton Curry (Lamb Curry).jpg` binds to `Mutton Curry`) and treats every
ambiguity as a hard error, because a card wearing the wrong dish's photo is worse
than a card with none: nothing downstream can detect it.

The photo sits in a fixed 16:9 box with `object-fit: cover`. The set is not
uniform — 52 of the 155 files are 16:9, 51 are 3:2, 8 are 4:3, across 53 distinct
pixel sizes — so letting each file set its own height would give the grid ragged
rows and a reflow as each image arrived. A 3:2 box was measured against 16:9 and
comes out level on how much of the set it crops, so card density decided it; 66
files are not cropped at all, and the two square photos lose 44% of their height,
which makes them the ones to replace first. The loading skeleton reserves the same
box. `alt` is empty by design: the photo says nothing the `<h3>` beside it does
not, and an empty `alt` is how you say "decorative here" instead of leaving it
unlabelled.

---

## Testing

421 tests, stdlib `unittest`, no ML dependencies and no network required:

```
tests/test_nlu.py             negation scoping, typos, facets, word boundaries, budgets   (70)
tests/test_places.py          geometry, providers, cache, confidence, degradation        (117)
tests/test_pricing.py         bands, rounding, tiers, staleness, dataset cross-check      (47)
tests/test_search_service.py  full pipeline with a stubbed encoder and reranker           (46)
tests/test_retrieval.py       BM25 correctness, RRF, normalisation, MMR                   (42)
tests/test_corpus.py          loading, tagging, false-positive regressions, health engine (41)
tests/test_ranking.py         hard filters, additive scoring, end-to-end constraints       (34)
tests/test_recommend.py       label encoding, preference matching, degradation             (24)
```

The pipeline is testable because the bi-encoder and cross-encoder sit behind
narrow interfaces. `test_search_service.py` substitutes deterministic stubs and
exercises the real orchestrator — filters, fusion, reranking, MMR, caching,
response shape — verifying wiring and contracts rather than model quality. The
venue layer is tested the same way: a stub provider covers the finder, and the
real providers are exercised on query construction and response parsing against
captured payload shapes.

Writing `test_nlu.py`'s budget cases surfaced four defects in the parser, each now
pinned by a `test_regression_*` case: "under 1,000 rupees" read as Rs 1 once the
thousands separator became a space; the repair for that — rejoining adjacent
three-digit groups — turned "top 10 500" into Rs 10,500 and destroyed "300-800"
entirely; "budget 1500" parsed to nothing; and a currency word was attached to a
number two positions away, across another number, so "top 10 500 rupees" landed on
a Rs 10 ceiling. Separators and ranges are now handled on the raw text, where the
character that distinguishes the cases is still visible.

`npm run verify` is a static check — it proves every file parses, every import
resolves, every `className` exists, and every dish has exactly one photo and every
photo exactly one dish. None of that would catch a null price dereferenced or a
payload key the client forgets to read. The client was therefore also
server-rendered with `react-dom/server` against payloads copied from the running
API, which is what surfaced bug 23: the price tag, food card, venue list, location
bar and insights panel all render, but only the panel's budget chip was missing.
The same harness covers the photos from the other side — that the `src` a card
actually renders resolves to a file on disk, for all 155 dishes, which the static
check cannot see because it verifies the rule rather than the rendered attribute.
That harness lives outside the repository because the installed `node_modules` here
carries win32 esbuild binaries, so `vite build` cannot run in this environment; a
proper client test suite is the obvious follow-up once the toolchain is
installable.

Every test above was written against behaviour probed first, then checked for
falsifiability: after a green run the app was deliberately mutated — a changed
coarsening precision, a dropped field from the Google mask, a deleted budget echo,
a slug rule that stopped collapsing punctuation, a renamed dish left with its old
photo — to confirm the intended assertion fails, and that it fails alone. A test
that has never failed has not been shown to test anything.

> ### Verification status
>
> The environment this upgrade was authored in had **no package-registry access**
> (both PyPI and npm returned 403) and **no outbound network access**.
> Consequently:
>
> - **Verified by execution:** all 421 backend tests, covering query
>   understanding, tagging, the health engine, BM25, RRF, MMR, hard filters,
>   additive scoring, budgets, the price model, the venue finder and both
>   providers' query/parse paths, the recommender's rule path, and the full search
>   orchestrator via stubs. Plus static checks on the client — JSX parsing,
>   import/export resolution, CSS class coverage, dish-to-photo coverage in both
>   directions — and a 69-check `renderToString` harness over the price, photo,
>   card, dialog, venue, location and query-insight components.
> - **Not verified by execution:** anything requiring an installed package or a
>   live host — actual `sentence-transformers` / FAISS / XGBoost calls, FastAPI
>   request handling, `vite build`, and **real Overpass or Google Places
>   responses**. The provider clients are written against the documented request
>   and response shapes and carefully reviewed, but no live call has been made.
>
> Please run `pip install -r backend/requirements.txt`, `npm install`, and both
> test commands once before merging. For the venue layer, the first live call is
> the thing to watch: check `provider_error` and `degraded` on
> `POST /dishes/{name}/venues`, and `GET /health` for the places stage.
