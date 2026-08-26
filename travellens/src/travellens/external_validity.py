"""
LostinSriLanka -- external validity: do our complaint rates track a signal we
did not produce?

Why this matters more than another internal score
-------------------------------------------------
Open problem #1 is that every evaluation label in this project was produced by
the assistant that built the pipeline. Nothing measured inside the project can
fix that, and this module does not claim to. What it can do is compare our
output against a number nobody here had any hand in: the public Google star
rating for the same place, and the count of ratings behind it.

If destinations we call heavily complained-about also rate poorly with the
travelling public, that is weak independent corroboration -- weak, because a
star rating measures overall satisfaction while this project measures
aspect-specific complaints, and the two are related but not the same quantity.
If the correlation were absent or backwards, that would be a real warning.

What this is NOT
----------------
Not a substitute for the human gold set. A correlation with star ratings
cannot tell you whether a particular segment was labelled correctly, only
whether the aggregate points the same way as an outside measure. Reported as
corroboration, never as accuracy.

Also a denominator
------------------
aggregate.py notes that popular places score high simply because more people
wrote about them. userRatingCount is an exposure measure collected
independently of our corpus, so a complaint rate can be checked against how
busy a place actually is rather than against how many reviews we happened to
scrape.

Cost and licence
----------------
One Places API (New) call per destination, using the place_id already cached
by place_ids.py -- no search step, so this is the cheapest way to ask. Results
are cached; re-runs are free. Ratings are Google's content: they are used here
to compute a statistic and are not redistributed in the release bundle.

Run with:  python scripts/34_external_validity.py
"""
import json
import math
import os
from datetime import date
from typing import Dict, List, Optional

import pandas as pd

from . import config as C
from .place_ids import FATAL_STATUS, KeyRing, _ascii

DETAILS = "https://places.googleapis.com/v1/places/"
FIELD_MASK = "id,rating,userRatingCount"

CACHE_CSV = C.DATA_PROCESSED / "place_ratings.csv"
REPORT_JSON = C.REPORTS / "external_validity.json"

CACHE_COLUMNS = ["destination", "place_id", "rating", "user_rating_count",
                 "status", "fetched_on", "key"]

# Below this, a correlation is being computed from too few places to mean
# anything, and reporting one would be worse than reporting none.
MIN_PLACES = 12


def load_cache(path=None) -> pd.DataFrame:
    path = path or CACHE_CSV
    if not os.path.exists(str(path)):
        return pd.DataFrame(columns=CACHE_COLUMNS)
    df = pd.read_csv(path, encoding="utf-8")
    for col in CACHE_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[CACHE_COLUMNS]


def save_cache(df: pd.DataFrame, path=None) -> None:
    path = path or CACHE_CSV
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    df = df.drop_duplicates(subset="destination", keep="last")
    df[CACHE_COLUMNS].to_csv(path, index=False, encoding="utf-8")


def outstanding(place_ids: pd.DataFrame, cache: pd.DataFrame) -> List[Dict]:
    """Destinations with a place_id but no rating answer yet."""
    done = set(cache.loc[cache["status"] == "OK", "destination"].astype(str))
    out = []
    for r in place_ids.to_dict("records"):
        name, pid = str(r.get("destination", "")), str(r.get("place_id") or "")
        if pid and name not in done:
            out.append({"destination": name, "place_id": pid})
    return out


def collect(fetcher, keys, targets: List[Dict], verbose: bool = True,
            on_batch=None, flush_every: int = 10) -> List[Dict]:
    """One details call per destination. Same durability rules as place_ids:
    answers are handed to the caller as they arrive, because they are billed."""
    ring = keys if isinstance(keys, KeyRing) else KeyRing(
        [keys] if isinstance(keys, str) else list(keys))
    today = date.today().isoformat()
    rows, pending = [], []
    try:
        for t in targets:
            row = {"destination": t["destination"], "place_id": t["place_id"],
                   "rating": "", "user_rating_count": "", "status": "",
                   "fetched_on": today, "key": ring.label}
            try:
                while True:
                    r = fetcher.get(
                        DETAILS + t["place_id"],
                        headers={"X-Goog-Api-Key": ring.current,
                                 "X-Goog-FieldMask": FIELD_MASK})
                    payload = r.json()
                    err = payload.get("error") or {}
                    status = err.get("status", "") if err else ""
                    if status == "RESOURCE_EXHAUSTED" and ring.rotate():
                        if verbose:
                            print("    -- quota reached, switching to {}".format(
                                ring.label))
                        row["key"] = ring.label
                        continue
                    break
                if err:
                    row["status"] = status or "ERROR"
                    if row["status"] in FATAL_STATUS:
                        raise RuntimeError("details {}: {}".format(
                            row["status"], err.get("message", "no detail")))
                else:
                    # A place with no public rating is a real answer, not a
                    # failure: it is simply not rated. Recorded as OK with an
                    # empty rating so it is never re-billed.
                    row["status"] = "OK"
                    row["rating"] = payload.get("rating", "")
                    row["user_rating_count"] = payload.get("userRatingCount", "")
                if verbose:
                    print("    {:<34} {} ({} ratings)".format(
                        _ascii(t["destination"])[:32],
                        row["rating"] or row["status"],
                        row["user_rating_count"] or 0))
            except RuntimeError:
                rows.append(row)
                pending.append(row)
                raise
            except Exception as exc:
                row["status"] = "ERROR_" + type(exc).__name__
                if verbose:
                    print("    {:<34} failed: {}".format(
                        _ascii(t["destination"])[:32], type(exc).__name__))
            rows.append(row)
            pending.append(row)
            if on_batch and len(pending) >= flush_every:
                on_batch(list(pending))
                del pending[:]
    finally:
        if on_batch and pending:
            on_batch(list(pending))
            del pending[:]
    return rows


# --------------------------------------------------------------------------
# The comparison
# --------------------------------------------------------------------------
def _spearman(a: List[float], b: List[float]) -> Optional[float]:
    """Rank correlation, computed here to avoid adding a scipy dependency.

    Rank rather than Pearson: a star rating is bounded at 5 and piles up near
    4.5, so the relationship with a complaint rate is monotonic long before it
    is linear.
    """
    n = len(a)
    if n < MIN_PLACES:
        return None
    ra, rb = _ranks(a), _ranks(b)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    da = sum((x - ma) ** 2 for x in ra) ** 0.5
    db = sum((y - mb) ** 2 for y in rb) ** 0.5
    if not da or not db:
        return None
    return round(num / (da * db), 3)


def _significance(rho: Optional[float], n: int) -> Optional[Dict]:
    """Two-sided p for a rank correlation, via Fisher's z.

    Reported because several of these correlations are computed over ~100
    destinations, where a rho of 0.1 is indistinguishable from nothing.
    Quoting the coefficient without it would invite a reader to treat noise as
    a weak effect. The normal approximation is adequate at these n; it is not
    adequate below about 30, and _spearman already refuses those.
    """
    if rho is None or n < 4 or abs(rho) >= 1:
        return None
    z = 0.5 * math.log((1 + rho) / (1 - rho)) * math.sqrt(n - 3)
    # Two-sided normal tail.
    p = math.erfc(abs(z) / math.sqrt(2))
    return {"p_value": round(p, 4), "significant_at_05": bool(p < 0.05)}


def _ranks(values: List[float]) -> List[float]:
    """Average ranks, so ties do not distort the correlation."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            out[order[k]] = avg
        i = j + 1
    return out


def correlate(cache: pd.DataFrame, scorecards: pd.DataFrame) -> Dict:
    """Complaint rate vs public star rating, overall and per aspect.

    A negative correlation is the expected direction: more complaints, lower
    stars.
    """
    rated = cache[(cache["status"] == "OK") & (cache["rating"] != "")].copy()
    rated["rating"] = pd.to_numeric(rated["rating"], errors="coerce")
    rated["user_rating_count"] = pd.to_numeric(
        rated["user_rating_count"], errors="coerce")
    rated = rated.dropna(subset=["rating"])
    stars = dict(zip(rated["destination"].astype(str), rated["rating"]))
    counts = dict(zip(rated["destination"].astype(str),
                      rated["user_rating_count"]))

    out = {"n_destinations_rated": len(stars), "aspects": {}}

    def pair(df):
        xs, ys = [], []
        for r in df.to_dict("records"):
            d = str(r.get("destination", ""))
            if d in stars and r.get("complaint_rate") is not None:
                xs.append(float(r["complaint_rate"]))
                ys.append(float(stars[d]))
        return xs, ys

    for aspect, grp in scorecards.groupby("aspect"):
        xs, ys = pair(grp)
        rho = _spearman(xs, ys) if xs else None
        out["aspects"][str(aspect)] = {
            "n": len(xs),
            "spearman_rate_vs_stars": rho,
            "significance": _significance(rho, len(xs)),
        }

    # Overall: one complaint rate per destination, weighted by opinions.
    if "n_negative" in scorecards.columns and "n_opinions" in scorecards.columns:
        agg = scorecards.groupby("destination").agg(
            n_negative=("n_negative", "sum"), n_opinions=("n_opinions", "sum"))
        agg = agg[agg["n_opinions"] > 0]
        agg["complaint_rate"] = agg["n_negative"] / agg["n_opinions"]
        agg = agg.reset_index()
        xs, ys = pair(agg)
        rho = _spearman(xs, ys) if xs else None
        out["overall"] = {
            "n": len(xs),
            "spearman_rate_vs_stars": rho,
            "significance": _significance(rho, len(xs)),
        }
        # Exposure: does our corpus size track how busy a place actually is?
        cs, gs = [], []
        for r in agg.to_dict("records"):
            d = str(r["destination"])
            if d in counts and pd.notna(counts[d]):
                cs.append(float(r["n_opinions"]))
                gs.append(float(counts[d]))
        vrho = _spearman(cs, gs) if cs else None
        out["corpus_vs_public_volume"] = {
            "n": len(cs),
            "spearman": vrho,
            "significance": _significance(vrho, len(cs)),
        }
    return out


def save(report: Dict, path=None) -> str:
    path = path or REPORT_JSON
    payload = {
        "what_this_is": (
            "Corroboration, not accuracy. Complaint rates produced by this "
            "project are rank-correlated against public Google star ratings, "
            "which nobody here produced. A star rating measures overall "
            "satisfaction and this project measures aspect-specific "
            "complaints, so agreement is weak evidence that the pipeline "
            "points the right way -- it says nothing about whether any "
            "individual label is correct. That still needs the human gold "
            "set (open problem #1)."),
        "expected_direction": "negative: more complaints, fewer stars",
        "results": report,
    }
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, ensure_ascii=False)
    return str(path)
