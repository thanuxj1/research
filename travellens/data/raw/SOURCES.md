# Data Provenance — LostinSriLanka

Status of every input this project uses. Written to be pasted into the thesis
and the dataset datasheet.

**Rule applied throughout:** where a source is confirmed it is cited; where it
is not, it is marked UNCONFIRMED rather than guessed at. An invented citation
is worse than an admitted gap.

---

## 1. Google Maps corpus — `Destination Reviews_(raw).csv`

| | |
|---|---|
| Rows used | 30,705 (of 37,415 raw) |
| Fields | Destination, District, Timespan, Review |
| Ratings | **none** |
| Timestamps | relative strings only ("4 years ago") |
| Coverage | 236 destinations, 12 districts |

**Source: CONFIRMED (high confidence)**

Kaggle — *Travel destinations reviews in Sri Lanka* ("Exploring Sri Lanka:
Unveiling Destination Delights Through Traveler Reviews"), user `nethumdperera`.
<https://www.kaggle.com/datasets/nethumdperera/travel-destinations-reviews-in-sir-lanka>

**Evidence for the match:** the dataset's stated update date is 25 March 2024;
the file timestamps inside the downloaded archive are `2024-03-25 13:37`. The
column signature (Destination / District / Timespan / Review) and the paired
raw + cleaned files both match.

**Before citing, verify:** open the Kaggle page and confirm the row count and
the two-file structure. Record the licence stated there — it governs what you
may redistribute.

---

## 2. TripAdvisor corpus — `Reviews.csv`

| | |
|---|---|
| Rows used | 16,149 (of 16,156) |
| Fields | Location_Name, Located_City, Location, Location_Type, User_ID, User_Location, User_Locale, User_Contributions, Travel_Date, Published_Date, Rating, Helpful_Votes, Title, Text |
| Ratings | **1–5 stars on every row** |
| Timestamps | absolute, 2011-03-12 to 2023-05-20 |
| Coverage | 76 locations, 36 cities, 18 districts |

**Source: UNCONFIRMED**

No source URL is recorded anywhere in this repository. A web search did not
identify a Kaggle dataset matching this column signature. Several TripAdvisor
datasets exist but none was confirmed as this one.

**Do not cite a URL for this dataset until it is verified.** To recover it:

1. Browser download history — search for `Reviews.csv` or the archive that
   contained it, and check the originating domain.
2. Kaggle account → *Recently Viewed* / *Downloads*.
3. Search Kaggle for the exact column name `Located_City`, which is unusual
   enough to be distinctive.

If the source cannot be recovered, say so in the datasheet: *"secondary dataset
of TripAdvisor reviews obtained from a public repository; original collection
methodology not documented."* That is an honest limitation. A fabricated
citation is academic misconduct.

---

## 3. District boundaries — `sri_lanka_districts.geojson`

**Source: CONFIRMED (documented in the file's own properties)**

`thejeshgn/srilanka` — electoral_districts_map, derived from GADM 2.7 LKA_adm1,
simplified. Licence: **CC-BY** — attribution required.

22 polygons. This project holds review data for 19 of them after the
TripAdvisor merge; the rest render as "no data".

---

## 4. Models used (not trained by this project)

| Method | Model | Trained by | On |
|---|---|---|---|
| B, C | `distilbert-base-uncased-finetuned-sst-2-english` | HuggingFace / Stanford SST-2 | film reviews |
| D, E | `cardiffnlp/twitter-roberta-base-sentiment-latest` | Cardiff NLP | tweets |

Both are applied zero-shot. Neither was trained on Sri Lankan tourism text.
Cite both in the thesis; neither is a contribution of this project.

---

## ⚠️ Documentation error carried over from earlier work

`docs/FULL_SYSTEM_DOCUMENTATION.md` line 171 states:

> | Destination Reviews (final) | `dataset/Destination Reviews (final).csv` | 3.7 MB | 16,156 TripAdvisor reviews, cleaned & labeled |

**This is wrong on two counts.** That file contains **35,434 rows**, not 16,156,
and it is **not** TripAdvisor data — it has no ratings, no user fields, and only
relative timestamps. The 16,156 figure belongs to `Reviews.csv`, which *is*
TripAdvisor.

The ingestion code read the right file; only the documentation was wrong.
Recorded here because the same mislabelling could otherwise be carried into
a write-up, where an examiner opening the file would find the row count does
not match.

**Fix the doc before submission.** If that table is reproduced in a thesis, an
examiner who opens the file will find the row count doesn't match, and every
other number in the document becomes suspect.

---

## What must go in the datasheet

- [ ] Confirm and record the Kaggle licence for source 1
- [ ] Recover or formally mark UNCONFIRMED the source for 2
- [ ] Attribute the GeoJSON (CC-BY) — required by its licence
- [ ] Cite both models
- [ ] State that review **text** is third-party content; this project's
      contribution is the derived labels, not the text
- [ ] Correct the row-count error above
