"""
LostinSriLanka -- destination identity via Google place_id.

The problem this solves
-----------------------
canonical.py groups destination names by a normalised string key and refuses
to guess beyond that: an under-merge loses some data, an over-merge invents a
place that does not exist. That caution is correct, and it leaves real
duplicates unmerged, because a string key cannot know that "Sembuwatta Lake"
and "Sembuwatta Lake, Elkaduwa" are one place while "Galle Fort" and "Galle
Fort Clock Tower" are two.

Google assigns every place a stable identifier. Two names that resolve to the
same place_id are the same place on an external authority's say-so, not on our
heuristic's. That turns a judgement call in the write-up into a citation.

What this module does NOT do
----------------------------
It does not merge anything on its own. Find Place will happily match a mistyped
or fictional destination to whatever is nearest, so an unreviewed place_id is
no safer than an unreviewed fuzzy match. The default run resolves ids, compares
them against the string-key grouping, and writes a proposal. Merging the corpus
requires --apply, and groups whose names share no identifying word are held back
for a human to read first.

Which API
---------
Places API (NEW), searchText. The legacy findplacefromtext endpoint that
collect.py uses returns REQUEST_DENIED on any Google Cloud project created
after the 2025 cutover -- legacy Places can no longer be enabled, so a project
with a working key still cannot call it. Verified against this project's key:
the legacy call failed, the same query on the new endpoint succeeded.

Cost
----
One searchText call per unresolved destination, with an explicit field mask
asking only for the id, the display name and the address -- enough to audit a
merge, and the cheapest tier that still lets you check the answer. Results are
cached in data/processed/place_ids.csv, so a second run costs nothing: only
destinations with no cached row are sent. Every run prints its call count.

Licence note
------------
place_id is the one field Google permits storing indefinitely; the cached name
and address are kept only so a merge can be audited, and are not published in
the release bundle. Coordinates are deliberately NOT requested here -- the map
overlay is OpenStreetMap (ODbL) and mixing the two would breach both licences.

Run with:
    python scripts/30_resolve_place_ids.py                 # resolve + propose
    python scripts/30_resolve_place_ids.py --apply         # also merge corpus
"""
import json
import os
from datetime import date
from typing import Dict, List, Optional

import pandas as pd

from . import canonical
from . import config as C

SEARCH_TEXT = "https://places.googleapis.com/v1/places:searchText"

CACHE_CSV = C.DATA_PROCESSED / "place_ids.csv"
REPORT_JSON = C.REPORTS / "place_id_resolution.json"

# "key" records WHICH key answered, never the key itself. A corpus assembled
# across several projects should say so in its own data, not only in a commit
# message -- if the provenance chapter has to explain the arrangement, the
# evidence for it should be in the file.
CACHE_COLUMNS = ["destination", "place_id", "matched_name",
                 "formatted_address", "status", "resolved_on", "key"]

# Asked of the API. places.id alone is the cheapest SKU, but an id you cannot
# sanity-check is useless for a merge you have to defend, so the display name
# and address are worth the tier. Note what is absent: places.location. The
# map overlay is OpenStreetMap (ODbL) and Google coordinates must not enter
# the pipeline, so we do not even receive them.
FIELD_MASK = "places.id,places.displayName,places.formattedAddress"

# Words that carry no identity, so their presence does not count as agreement
# between two variant names. "Jungle Beach" and "Unawatuna Beach" share
# "beach" and nothing that matters.
_STOPWORDS = {"national", "park", "beach", "lake", "temple", "falls",
              "waterfall", "fort", "point", "view", "rock", "bay", "island",
              "garden", "gardens", "museum", "tower", "sri", "lanka"}

# Errors that mean the credentials, the enabled APIs or the billing account
# are wrong, not the destination. They stop the run rather than being cached
# as "not found" -- 300 cached failures would cost money and teach nothing.
FATAL_STATUS = ("PERMISSION_DENIED", "UNAUTHENTICATED", "RESOURCE_EXHAUSTED",
                "INVALID_ARGUMENT", "FAILED_PRECONDITION")


# --------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------
def load_cache(path=None) -> pd.DataFrame:
    """Previously resolved destinations. Empty frame if none."""
    path = path or CACHE_CSV
    if not os.path.exists(str(path)):
        return pd.DataFrame(columns=CACHE_COLUMNS)
    df = pd.read_csv(path, encoding="utf-8")
    for col in CACHE_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[CACHE_COLUMNS].fillna("")


def save_cache(df: pd.DataFrame, path=None) -> None:
    """Write the cache, one row per destination.

    A retried destination appends a second row; the later one is the answer we
    just paid for, so it wins. Only failures are ever retried, so this can
    never discard an OK in favour of an error.
    """
    path = path or CACHE_CSV
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    df = df.drop_duplicates(subset="destination", keep="last").copy()
    # A cache written before a column existed is still a valid cache. Refusing
    # to save it would mean re-billing every row it holds.
    for col in CACHE_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df[CACHE_COLUMNS].fillna("").to_csv(path, index=False, encoding="utf-8")


ANSWERED = ("OK", "ZERO_RESULTS")


def unresolved(names: List[str], cache: pd.DataFrame) -> List[str]:
    """Destinations Google has not actually answered yet.

    ZERO_RESULTS counts as answered: asking the same question again costs
    money and returns the same reply. Delete the row to force a retry.

    PERMISSION_DENIED, a timeout, or any other failure does NOT count. Those
    say something about our project or our network, not about the place, and a
    run that died half way must be resumable once the cause is fixed --
    otherwise the failure is cached forever and the destination is silently
    dropped from the corpus.
    """
    known = set(cache.loc[cache["status"].isin(ANSWERED), "destination"]
                .astype(str))
    out, seen = [], set()
    for n in names:
        n = str(n)
        if n in known or n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out


# --------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------
def _ascii(text: str) -> str:
    """Printable form of a name.

    Windows consoles and redirected stdout default to cp1252, and the corpus
    carries mojibake from the original scrape -- one destination contains
    U+FFFD. A crash inside a progress message would throw away every billed
    call made so far, so nothing unprintable is ever handed to print().
    """
    return str(text).encode("ascii", "replace").decode("ascii")


class KeyRing(object):
    """Keys tried in order, advancing when one exhausts its daily quota.

    A per-project daily cap stops a run part-way; a second project's key
    carries it on. Note what this is: spreading one job across projects to
    exceed a quota Google set per project. It is done here because the project
    owner asked for it knowing that, not because it is the tidy answer -- the
    supported route is a quota increase, and the free one is to resume the run
    tomorrow. Whichever key answered a destination is recorded, so the run is
    auditable rather than merely effective.
    """

    def __init__(self, keys: List[str]):
        self.keys = [k for k in keys if k]
        if not self.keys:
            raise ValueError("no usable keys")
        self.i = 0

    @property
    def current(self) -> str:
        return self.keys[self.i]

    @property
    def label(self) -> str:
        """How the run refers to a key. Never the key itself."""
        return "key {} of {}".format(self.i + 1, len(self.keys))

    def rotate(self) -> bool:
        """Advance to the next key. False when none is left."""
        self.i += 1
        return self.i < len(self.keys)

    def headers(self) -> Dict[str, str]:
        return {"X-Goog-Api-Key": self.current, "X-Goog-FieldMask": FIELD_MASK}


def resolve_names(fetcher, key, names: List[str], verbose: bool = True,
                  on_batch=None, flush_every: int = 10) -> List[Dict]:
    """One searchText call per name. Returns cache rows, resolved or not.

    key is one key or a list of them; a list rotates on RESOURCE_EXHAUSTED and
    the name that triggered it is retried on the next key rather than lost.

    on_batch, if given, receives rows as they arrive and is called again from
    a finally block. Every call here is billed, so a crash or a quota wall two
    hundred names in must not discard the two hundred answers already paid
    for. The caller persists what it is handed; this function never returns
    the only copy.
    """
    ring = key if isinstance(key, KeyRing) else KeyRing(
        [key] if isinstance(key, str) else list(key))
    today = date.today().isoformat()
    # Mutated in place, never rebound, so the finally block below sees
    # everything collected up to the moment of a failure.
    rows, pending = [], []
    try:
        _resolve_loop(fetcher, ring, names, today, verbose,
                      on_batch, flush_every, rows, pending)
    finally:
        if on_batch and pending:
            on_batch(list(pending))
            del pending[:]
    return rows


def _resolve_loop(fetcher, ring, names, today, verbose, on_batch,
                  flush_every, rows, pending) -> None:
    for name in names:
        row = {"destination": name, "place_id": "", "matched_name": "",
               "formatted_address": "", "status": "", "resolved_on": today,
               "key": ring.label}
        try:
            while True:
                # regionCode biases the search to Sri Lanka, which matters:
                # several destination names in the corpus also name places in
                # India.
                r = fetcher.post_json(SEARCH_TEXT, {
                    "textQuery": "{} Sri Lanka".format(name),
                    "regionCode": "LK",
                    "languageCode": "en",
                    "maxResultCount": 1}, headers=ring.headers())
                payload = r.json()
                err = payload.get("error") or {}
                status = err.get("status", "") if err else ""

                # A spent key is not a failed destination. Move to the next
                # key and ask again -- the name is retried, never consumed by
                # the rotation.
                if status == "RESOURCE_EXHAUSTED" and ring.rotate():
                    if verbose:
                        print("    -- daily quota reached, switching to {}"
                              .format(ring.label))
                    row["key"] = ring.label
                    continue
                break

            if err:
                row["status"] = status or "ERROR"
                if row["status"] in FATAL_STATUS:
                    raise RuntimeError("searchText {}: {}".format(
                        row["status"], err.get("message", "no detail")))
            else:
                places = payload.get("places") or []
                row["status"] = "OK" if places else "ZERO_RESULTS"
                if places:
                    row["place_id"] = places[0].get("id", "")
                    row["matched_name"] = (
                        places[0].get("displayName") or {}).get("text", "")
                    row["formatted_address"] = places[0].get(
                        "formattedAddress", "")
            if verbose:
                print("    {:<34} {}".format(
                    _ascii(name)[:32],
                    _ascii(row["matched_name"] or row["status"])))
        except RuntimeError:
            rows.append(row)
            pending.append(row)
            raise
        except Exception as exc:
            row["status"] = "ERROR_" + type(exc).__name__
            if verbose:
                print("    {:<34} failed: {}".format(
                    _ascii(name)[:32], type(exc).__name__))
        rows.append(row)
        pending.append(row)
        if on_batch and len(pending) >= flush_every:
            on_batch(list(pending))
            del pending[:]


# --------------------------------------------------------------------------
# Comparison against the string-key grouping
# --------------------------------------------------------------------------
def _identity_tokens(name: str) -> set:
    return set(canonical.destination_key(name).split()) - _STOPWORDS


def _display_name(variants: List[str], counts: Dict[str, int],
                  matched_name: str) -> str:
    """Which spelling the dashboard shows for a merged group.

    canonical._preferred() ranks capitalisation first, which is right when the
    only difference is casing and wrong when one variant carries a locality
    suffix: it prefers "Jungle Beach, Unawatuna" over "Jungle Beach" purely for
    having a third capital letter. We already paid for the name Google matched,
    and it is the same authority the merge itself rests on, so it breaks the
    tie -- but only by selecting among spellings the corpus actually contains.
    Inventing a display name no reviewer ever wrote would put a place on the
    dashboard that appears nowhere in the data.
    """
    override = canonical.DISPLAY_OVERRIDES.get(
        canonical.destination_key(variants[0]))
    if override:
        return override
    if matched_name:
        key = canonical.destination_key(matched_name)
        for v in variants:
            if canonical.destination_key(v) == key:
                return v
    return canonical._preferred({v: counts.get(v, 0) for v in variants})


def district_index(destinations: pd.Series,
                   districts: pd.Series) -> Dict[str, set]:
    """destination -> the districts its reviews are filed under."""
    out = {}
    for dest, dist in zip(destinations.astype(str), districts):
        if pd.isna(dist) or not str(dist).strip():
            continue
        out.setdefault(dest, set()).add(str(dist).strip())
    return out


def propose_merges(cache: pd.DataFrame, destinations: pd.Series,
                   districts: Optional[pd.Series] = None) -> Dict:
    """Group destinations by place_id and score each group against canonical.py.

    Every group of two or more names sharing an id is one of:
      agreed        the string key already merged these -- no new information
      new           place_id joins names the string key kept apart -- the win
      needs_review  a new merge whose names share no identifying word, which
                    is what an over-merge looks like from the outside

    Nothing is applied from here; the caller decides which kinds to act on.
    """
    counts = destinations.dropna().astype(str).value_counts().to_dict()
    string_map = canonical.build_map(destinations)
    by_district = (district_index(destinations, districts)
                   if districts is not None else {})

    by_id = {}
    matched = {}
    for row in cache.to_dict("records"):
        pid = str(row.get("place_id") or "")
        name = str(row.get("destination") or "")
        if not pid or name not in counts:
            continue
        by_id.setdefault(pid, []).append(name)
        if str(row.get("matched_name") or ""):
            matched[pid] = str(row["matched_name"])

    groups = []
    for pid, variants in by_id.items():
        variants = sorted(set(variants), key=lambda v: -counts.get(v, 0))
        if len(variants) < 2:
            continue
        already = set(string_map.get(v, v) for v in variants)
        shared = set.intersection(*[_identity_tokens(v) for v in variants])
        google = matched.get(pid, "")

        # Does Google's own name for this place match any name we hold? When
        # it does not, the id may be pointing at a NEIGHBOUR rather than at
        # our place. The real case: "Ravana Waterfall" and "Ravana Ella Falls"
        # both resolved to "Kuda Ravana Ella waterfall", a different and
        # smaller fall nearby. The two may well be one place, but this id is
        # not the evidence for it, and a merge justified by the wrong
        # identifier is worse than an honest under-merge.
        gkey = canonical.destination_key(google) if google else ""
        recognised = any(canonical.destination_key(v) == gkey for v in variants)

        # Do the variants even sit in the same part of the country? The
        # corpus files every review under a district, so this costs nothing
        # and catches what no name comparison can. The real case: 'Maritime
        # Museum' is filed under Galle and resolved to a Colombo address --
        # the Galle maritime museum matched to the Colombo one, which would
        # have moved 204 reviews to the wrong place with every other guard
        # satisfied.
        spans = set()
        for v in variants:
            spans |= by_district.get(v, set())

        kind = "agreed" if len(already) == 1 else "new"
        reason = ""
        if kind == "new" and len(spans) > 1:
            kind, reason = "needs_review", (
                "variants are filed under different districts: "
                + ", ".join(sorted(spans)))
        elif kind == "new" and not shared:
            kind, reason = "needs_review", "variants share no identifying word"
        elif kind == "new" and google and not recognised:
            kind, reason = "needs_review", (
                "Google calls this place {!r}, which is none of our"
                " names".format(google))

        groups.append({
            "place_id": pid,
            "kind": kind,
            "reason": reason,
            "canonical": _display_name(variants, counts, google),
            "matched_name": google,
            "matched_a_variant": bool(recognised),
            "variants": variants,
            "reviews": {v: int(counts.get(v, 0)) for v in variants},
            "shared_words": sorted(shared),
            "districts": sorted(spans),
        })

    # Names the string key merged but Google says are different places. We
    # never act on this -- unmerging would need its own justification -- but a
    # silent disagreement between the two methods is exactly what a reader
    # would want flagged.
    ids = {str(r["destination"]): str(r.get("place_id") or "")
           for r in cache.to_dict("records")}
    by_canon = {}
    for variant, canon in string_map.items():
        by_canon.setdefault(canon, []).append(variant)
    conflicts = []
    for canon, variants in by_canon.items():
        seen = set(ids.get(v, "") for v in variants if ids.get(v))
        if len(seen) > 1:
            conflicts.append({"canonical": canon,
                              "variants": sorted(variants),
                              "place_ids": sorted(seen)})

    groups.sort(key=lambda g: (g["kind"] != "new", -sum(g["reviews"].values())))
    return {"groups": groups, "conflicts": conflicts}


def mapping_from_groups(groups: List[Dict],
                        include_review: bool = False) -> Dict[str, str]:
    """variant -> canonical display name, for groups we are willing to act on."""
    kinds = {"new", "agreed"}
    if include_review:
        kinds.add("needs_review")
    out = {}
    for g in groups:
        if g["kind"] not in kinds:
            continue
        for v in g["variants"]:
            out[v] = g["canonical"]
    return out


def apply_mapping(mapping: Dict[str, str], corpus_path=None,
                  verbose: bool = True) -> Dict:
    """Rewrite the destination column of the stored corpus."""
    corpus_path = corpus_path or C.CLEAN_REVIEWS_CSV
    df = pd.read_csv(corpus_path, encoding="utf-8")
    before = df["destination"].nunique()
    df["destination"] = df["destination"].map(lambda d: mapping.get(d, d))
    after = df["destination"].nunique()
    df.to_csv(corpus_path, index=False, encoding="utf-8")
    if verbose:
        print("  destinations: {} -> {}".format(before, after))
        print("  wrote {}".format(corpus_path))
    return {"destinations_before": int(before),
            "destinations_after": int(after)}


# --------------------------------------------------------------------------
# Per-group decisions
# --------------------------------------------------------------------------
# Why a decisions file rather than a cleverer guard: the guards trade one kind
# of error for the other and cannot tell a toponym that identifies a place
# ("Narangala") from one that merely locates it ("Hambantota"). With fifteen
# groups, reading them is a two-minute job that produces a defensible answer
# per place. The file records WHO decided WHAT and WHY, survives a re-run, and
# can be edited by hand -- which a threshold cannot.
DECISIONS_JSON = C.REPORTS / "place_id_decisions.json"

MERGE = "merge"
KEEP_APART = "keep_apart"
UNDECIDED = "undecided"


def load_decisions(path=None) -> Dict[str, Dict]:
    path = path or DECISIONS_JSON
    if not os.path.exists(str(path)):
        return {}
    with open(str(path), encoding="utf-8") as fh:
        return json.load(fh).get("decisions", {})


def decisions_template(groups: List[Dict],
                       existing: Optional[Dict] = None) -> Dict:
    """A decision slot per group, keeping any answer already recorded.

    A group whose guards all passed is pre-filled with 'merge'; anything held
    for review starts 'undecided', because that is what it is. Re-running
    resolution never silently overwrites a judgement already made.
    """
    existing = existing or {}
    out = {}
    for g in groups:
        prev = existing.get(g["place_id"], {})
        out[g["place_id"]] = {
            "decision": prev.get(
                "decision",
                MERGE if g["kind"] in ("new", "agreed") else UNDECIDED),
            "canonical": prev.get("canonical", g["canonical"]),
            "reason": prev.get("reason", g.get("reason", "")),
            "variants": g["variants"],
            "reviews": sum(g["reviews"].values()),
        }
    return out


def save_decisions(decisions: Dict, path=None) -> str:
    path = path or DECISIONS_JSON
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(str(path), "w", encoding="utf-8") as fh:
        json.dump({"decisions": decisions}, fh, indent=1, ensure_ascii=False)
    return str(path)


def mapping_from_decisions(groups: List[Dict], decisions: Dict):
    """(variant -> canonical, undecided groups).

    Only an explicit 'merge' moves a review. Undecided is not a soft yes.
    """
    mapping, undecided = {}, []
    for g in groups:
        d = decisions.get(g["place_id"], {})
        verdict = d.get("decision", UNDECIDED)
        if verdict == MERGE:
            canon = d.get("canonical") or g["canonical"]
            for v in g["variants"]:
                mapping[v] = canon
        elif verdict != KEEP_APART:
            undecided.append(g)
    return mapping, undecided


# --------------------------------------------------------------------------
# Auxiliary files keyed on destination name
# --------------------------------------------------------------------------
def remap_auxiliary(mapping: Dict[str, str], verbose: bool = True) -> Dict:
    """Carry the name-keyed side files through a merge.

    Coordinates and source links are stored per destination NAME, so merging
    two names silently orphans whichever entry belonged to the losing one.
    That is how three of the largest merged destinations lost their map pins:
    'Galle Fort' held the coordinates, 'Galle Dutch Fort' survived the merge,
    and the pin belonged to neither afterwards.

    A merged-away entry is moved to the canonical name only when the canonical
    has none of its own -- an existing entry is never overwritten.
    """
    moved = {"coordinates": [], "media": [], "segments": 0}

    coords_path = C.DATA_PROCESSED / "destination_coordinates.csv"
    if os.path.exists(str(coords_path)):
        cd = pd.read_csv(coords_path, encoding="utf-8")
        have = set(cd["destination"].astype(str))
        for old, canon in mapping.items():
            if old in have and canon not in have and old != canon:
                cd.loc[cd["destination"] == old, "destination"] = canon
                have.discard(old)
                have.add(canon)
                moved["coordinates"].append((old, canon))
        # A merged-away name whose canonical already had coordinates leaves a
        # dead row behind. Only those are dropped -- a coordinate for some
        # other destination the corpus has not seen yet is not our business.
        dead = cd["destination"].astype(str).isin(
            [old for old, canon in mapping.items() if old != canon])
        if int(dead.sum()):
            moved["dropped"] = sorted(cd.loc[dead, "destination"].astype(str))
            cd = cd[~dead]
        cd = cd.drop_duplicates(subset="destination", keep="first")
        cd.to_csv(coords_path, index=False, encoding="utf-8")

    # Storyboard media is accumulated from collectors and cannot be
    # regenerated from the corpus, so it is relabelled rather than rebuilt.
    # Left alone, media attached to a merged-away name simply stops appearing.
    media_path = C.DATA_PROCESSED / "media.csv"
    if os.path.exists(str(media_path)):
        md = pd.read_csv(media_path, encoding="utf-8")
        if "destination" in md.columns:
            hits = md["destination"].astype(str).isin(mapping)
            if int(hits.sum()):
                for old, canon in mapping.items():
                    n = int((md["destination"].astype(str) == old).sum())
                    if n:
                        moved["media"].append((old, canon, n))
                md["destination"] = md["destination"].astype(str).map(
                    lambda d: mapping.get(d, d))
                md.to_csv(media_path, index=False, encoding="utf-8")

    # segments_tagged_union.csv is NOT rebuilt by the refresh: it comes from
    # the embedding and trained-tagger steps (17, 19), which are expensive and
    # run on demand. So it keeps whatever destination names it was written
    # with, and the release bundle is built from it -- which is how the
    # citable artifact ended up carrying 308 pre-merge names while the corpus
    # had 294. The merge was a pure rename, so relabelling is exact: no
    # segment, tag or score changes.
    union_path = C.DATA_PROCESSED / "segments_tagged_union.csv"
    if os.path.exists(str(union_path)):
        ud = pd.read_csv(union_path, encoding="utf-8", low_memory=False)
        if "destination" in ud.columns:
            hits = int(ud["destination"].astype(str).isin(mapping).sum())
            if hits:
                ud["destination"] = ud["destination"].astype(str).map(
                    lambda d: mapping.get(d, d))
                ud.to_csv(union_path, index=False, encoding="utf-8")
                moved["segments"] = hits

    # destination_links.json is DERIVED from the corpus by provenance.py, so
    # it is not patched here -- rebuilding it is both cleaner and correct.
    # Merged-away entries sometimes hold a link the survivor lacks ('Galle
    # Fort' carried a TripAdvisor link that 'Galle Dutch Fort' did not), and a
    # rebuild recovers those instead of choosing between them.
    moved["links_note"] = "run scripts/22_build_provenance.py to rebuild"

    if verbose:
        for old, canon in moved["coordinates"]:
            print("    coordinates moved: {!r} -> {!r}".format(old, canon))
        for old, canon, n in moved["media"]:
            print("    media relabelled: {} item(s) {!r} -> {!r}".format(
                n, old, canon))
        if moved["segments"]:
            print("    segments relabelled: {} rows in "
                  "segments_tagged_union.csv".format(moved["segments"]))
        if not moved["coordinates"] and not moved["media"] and not moved["segments"]:
            print("    no coordinates, media or segments needed moving")
        print("    links: {}".format(moved["links_note"]))
    return moved
