# TravelLens LK — Annotation Guidelines

**Purpose.** These rules let two different people read the same review piece and
arrive at the same label. Consistency is the point: a gold set that one person
produced by instinct is not a measurement, it is an opinion.

Print this. Keep it beside you while labelling. If you change a rule half way
through, go back and re-label the rows you already did.

---

## What you are doing

You will see a **piece** of a review (one sentence or clause), and the **full
review** it came from. For each of the seven aspects, write one letter:

| Letter | Meaning |
|--------|---------|
| `N` | **Negative** — the visitor is complaining about this aspect |
| `P` | **Positive** — the visitor is praising this aspect |
| `X` | **Neutral** — the aspect is mentioned as a plain fact, no opinion |
| *(blank)* | Not mentioned at all |

Then put `x` in the **checked** column so you know the row is finished.

**Most cells will be blank.** A typical piece touches one or two aspects. That is
normal and expected.

---

## The seven aspects

| Aspect | Covers |
|---|---|
| `roads_access` | Road condition, distance, parking, buses/trains, difficulty of the walk or climb, finding the place |
| `facilities` | Toilets, changing rooms, food, shops, seating, shelter, bins, signage, guides, ticket counters |
| `cleanliness` | Litter, plastic, rubbish, smells, general upkeep |
| `safety` | Slippery ground, deep water, drowning, falls, wildlife, warnings to other visitors |
| `price_value` | Entrance fees, parking charges, food prices, value for money, local vs foreign pricing |
| `crowd` | Busy, queues, noise — and also peaceful/quiet |
| `scenery` | Views, landscape, waterfalls, wildlife sightings, sunrise/sunset |

---

## The seven rules

### Rule 1 — Judge the *piece*, but use the *full review* to understand it

The label describes the piece in front of you. The full review is there so you
know what the visitor meant.

> **Piece:** "If you pass by, its nice to stop."
> **Full review:** "Not that impressive ruins. If you pass by, its nice to stop.
> Otherwise not recommended to make a tour there"

The piece alone sounds positive. In context it is faint praise inside a negative
review. Label the piece as written — but if the context reverses the meaning
entirely, follow the context and write why in **notes**.

### Rule 2 — Praise counts. Do not only mark complaints.

This is the most common mistake. The system must learn the difference between
praise and complaint, so praise must be labelled too.

> "The toilets are clean and managed well." → `facilities = P`, `cleanliness = P`

If you skip the `P` labels, the model has nothing to contrast complaints
against, and every measurement you report will be wrong.

### Rule 3 — A request for improvement is Negative

If the visitor asks for something to be fixed, they are complaining, even
politely.

> "but need to clean the pond area and the surroundings." → `cleanliness = N`
> "Please keep this place clean." → `cleanliness = N`
>   *(they are saying it is not being kept clean)*

### Rule 4 — A rule or fact stated without opinion is `X`, not `N`

> "Officials discourage polythene and plastics so the environment is still
> protected." → `cleanliness = P` *(they approve of the rule)*
> "Entrance fee for one local is 150 LKR." → `price_value = X` *(pure fact)*
> "You need to enter before 2pm." → `X` on everything *(a fact, no opinion)*

Ask yourself: **is the visitor expressing a feeling, or reporting information?**

### Rule 5 — Warnings to other visitors are Negative safety

> "Be careful when it's raining." → `safety = N`
> "Bringing infants is bit risky." → `safety = N`

Even though the visitor may have enjoyed themselves, they are flagging a risk.
That is the signal we want to capture.

### Rule 6 — Hard difficulty is `N`; enjoyable challenge is `P`

> "difficult to access, need to drive 4km through tea estate" → `roads_access = N`
> "Great walk, well worth the climb" → `roads_access = P`
> "It is an 8 km walk" → `roads_access = X` *(fact, no opinion)*

If the visitor complains about the effort → `N`.
If the visitor enjoyed the effort → `P`.
If they simply state the distance → `X`.

### Rule 7 — When you genuinely cannot decide, leave blank and write why

Do not guess. Write the reason in **notes**. Disagreements and unclear cases
are findings in their own right — they belong in the thesis, not hidden.

---

## Worked examples

| Piece | Labels | Why |
|---|---|---|
| "Nice location" | `scenery=P` | praise of the place itself |
| "but bathing is dangerous here." | `safety=N` | explicit risk |
| "Parking facilities are available (60 rupees for a hour) and also toilet facilities are there." | `roads_access=X`, `facilities=X`, `price_value=X` | all three stated as fact, no opinion |
| "Dirty, noisy and expensive." | `cleanliness=N`, `crowd=N`, `price_value=N` | three complaints in four words |
| "Great view, good hike, people should not litter." | `scenery=P`, `roads_access=P`, `cleanliness=N` | praise, praise, complaint together |
| "35€ for a 4h walk where there are only 3 points of interest." | `price_value=N` | poor value |
| "Clean beach, lot of local food options" | `cleanliness=P`, `facilities=P` | both praise |
| "no one here to guide you but they ask to buy tickets" | `facilities=N`, `price_value=N` | missing service, charged anyway |
| "Everyone should try this place" | *(all blank)* | recommendation, no aspect |

---

## Quality control

1. **Do rows 1–150 first.** A second person labels the *same* 150 rows
   independently, using `goldset_annotator2.csv`. We then measure agreement
   (Cohen's kappa). Target **κ ≥ 0.6**; below that, the guidelines are unclear
   and must be revised before continuing.
2. **Never look at the other person's answers while labelling.**
3. **Label in short sessions.** Accuracy drops badly after about an hour. Aim
   for 100–150 rows per session.
4. **Never edit a label to make the model look better.** If you do, the
   evaluation is worthless and, if noticed, is academic misconduct.

---

## Time estimate

600 rows at roughly 15–20 seconds each ≈ **3 hours** for annotator 1,
plus **45 minutes** for annotator 2's 150-row overlap.

This is the single most valuable three hours of the entire project. Every
accuracy figure in your results chapter rests on it.
