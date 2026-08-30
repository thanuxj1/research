"""
Guard tests: place_id merging must never be automatic, and never silent.

The value of resolving destinations to Google place_ids is that a merge stops
being our judgement call. That only holds if an unsafe-looking group is held
back rather than applied, and if a disagreement between the two methods is
reported instead of swallowed. These tests fail loudly if either guarantee is
lost. No API key and no network access is needed -- the cache is synthetic.

Run:  python -m pytest tests/test_place_ids.py -q
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from travellens import place_ids as P  # noqa: E402

# A stand-in for data/processed/place_ids.csv.
#   ChIJjungle  one place the string key holds as two names -- the real case in
#               the corpus: 'Jungle Beach' (183) and 'Jungle Beach, Unawatuna'
#               (222) are one beach split into two destinations
#   ChIJmixed   two unrelated names sharing an id, which is what a bad Find
#               Place match looks like
CACHE = pd.DataFrame([
    {"destination": "Jungle Beach", "place_id": "ChIJjungle",
     "matched_name": "Jungle Beach", "formatted_address": "Unawatuna",
     "status": "OK", "resolved_on": "2026-08-25"},
    {"destination": "Jungle Beach, Unawatuna", "place_id": "ChIJjungle",
     "matched_name": "Jungle Beach", "formatted_address": "Unawatuna",
     "status": "OK", "resolved_on": "2026-08-25"},
    {"destination": "Sigiriya", "place_id": "ChIJmixed",
     "matched_name": "Sigiriya", "formatted_address": "Matale",
     "status": "OK", "resolved_on": "2026-08-25"},
    {"destination": "Galle Fort", "place_id": "ChIJmixed",
     "matched_name": "Sigiriya", "formatted_address": "Matale",
     "status": "OK", "resolved_on": "2026-08-25"},
    {"destination": "Ella Rock", "place_id": "",
     "matched_name": "", "formatted_address": "",
     "status": "ZERO_RESULTS", "resolved_on": "2026-08-25"},
])

DESTINATIONS = pd.Series(
    ["Jungle Beach"] * 183
    + ["Jungle Beach, Unawatuna"] * 222
    + ["Sigiriya"] * 400
    + ["Galle Fort"] * 300
    + ["Ella Rock"] * 50
)


def _groups():
    return {g["place_id"]: g
            for g in P.propose_merges(CACHE, DESTINATIONS)["groups"]}


def test_shared_id_with_a_shared_word_is_a_new_merge():
    """The case the string key misses and place_id catches."""
    g = _groups()["ChIJjungle"]
    assert g["kind"] == "new"
    assert set(g["variants"]) == {"Jungle Beach", "Jungle Beach, Unawatuna"}
    assert sum(g["reviews"].values()) == 405


def test_generic_words_do_not_count_as_agreement():
    """'beach' is shared by half the corpus, so it must not justify a merge."""
    assert "beach" not in _groups()["ChIJjungle"]["shared_words"]
    assert "jungle" in _groups()["ChIJjungle"]["shared_words"]


def test_unrelated_names_sharing_an_id_are_held_back():
    """A bad Find Place match must not become a merge."""
    assert _groups()["ChIJmixed"]["kind"] == "needs_review"


def test_needs_review_groups_are_excluded_by_default():
    """The default mapping applies only what can be justified."""
    groups = list(_groups().values())
    default = P.mapping_from_groups(groups)
    assert "Jungle Beach" in default
    assert "Galle Fort" not in default, "an unreviewed group reached the corpus"
    assert "Sigiriya" not in default

    forced = P.mapping_from_groups(groups, include_review=True)
    assert "Galle Fort" in forced, "--include-review must still be able to merge"


def test_unresolved_names_are_never_grouped():
    """ZERO_RESULTS is cached, but an empty id must not group anything."""
    assert "" not in _groups()
    for g in _groups().values():
        assert "Ella Rock" not in g["variants"]


def test_zero_results_rows_are_not_retried():
    """Re-asking a question Google already answered costs money."""
    assert P.unresolved(["Ella Rock", "Jungle Beach"], CACHE) == []
    assert P.unresolved(["Adams Peak"], CACHE) == ["Adams Peak"]


def test_string_key_merges_that_google_disputes_are_reported():
    """A disagreement between the two methods is surfaced, not swallowed."""
    cache = CACHE.copy()
    # Two spellings canonical.py merges on the strict key, given different ids.
    cache = pd.concat([cache, pd.DataFrame([
        {"destination": "Horton Plains National Park", "place_id": "ChIJa",
         "matched_name": "Horton Plains", "formatted_address": "Nuwara Eliya",
         "status": "OK", "resolved_on": "2026-08-25"},
        {"destination": "Horton plains national park", "place_id": "ChIJb",
         "matched_name": "Horton Plains", "formatted_address": "Nuwara Eliya",
         "status": "OK", "resolved_on": "2026-08-25"},
    ])], ignore_index=True)
    dests = pd.concat([DESTINATIONS, pd.Series(
        ["Horton Plains National Park"] * 193
        + ["Horton plains national park"] * 1007)])

    conflicts = P.propose_merges(cache, dests)["conflicts"]
    assert any(c["place_ids"] == ["ChIJa", "ChIJb"] for c in conflicts), \
        "the two methods disagree and nothing said so"


def test_coordinates_are_never_requested():
    """The map overlay is ODbL. Google coordinates must not enter the pipeline.

    The field mask is the enforcement point: what is not asked for is not
    received, so this cannot be undone by a careless read of the response.
    """
    for field in ("location", "geometry", "viewport"):
        assert field not in P.FIELD_MASK
    assert "location" not in P.CACHE_COLUMNS


def test_the_new_places_endpoint_is_used():
    """Legacy Places cannot be enabled on projects created after the 2025
    cutover, so a legacy URL here would fail for every new user of this repo."""
    assert P.SEARCH_TEXT.startswith("https://places.googleapis.com/v1/")
    assert "maps.googleapis.com/maps/api/place" not in P.SEARCH_TEXT


def test_google_name_breaks_the_display_tie():
    """'Jungle Beach' must win over 'Jungle Beach, Unawatuna'.

    canonical._preferred() would pick the suffixed variant for having one more
    capital letter, which is the wrong name to put on the dashboard.
    """
    assert _groups()["ChIJjungle"]["canonical"] == "Jungle Beach"


def test_a_display_name_is_always_one_the_corpus_contains():
    """Google's spelling may differ from every variant; it must not be invented."""
    cache = CACHE.copy()
    cache.loc[cache["destination"] == "Jungle Beach", "matched_name"] = \
        "Jungle Beach (Rumassala)"
    cache.loc[cache["destination"] == "Jungle Beach, Unawatuna", "matched_name"] = \
        "Jungle Beach (Rumassala)"
    groups = P.propose_merges(cache, DESTINATIONS)["groups"]
    g = [x for x in groups if x["place_id"] == "ChIJjungle"][0]
    assert g["canonical"] in set(DESTINATIONS)


class _Boom(Exception):
    pass


class _FakeFetcher:
    """Answers two names, then fails. Stands in for a run that dies mid-way."""

    def __init__(self, fail_after):
        self.fail_after = fail_after
        self.n = 0

    def post_json(self, url, body, headers=None, timeout=20):
        self.n += 1
        if self.n > self.fail_after:
            raise _Boom("network died")

        class R(object):
            @staticmethod
            def json():
                return {"places": [{"id": "ChIJ_x",
                                    "displayName": {"text": "Somewhere"},
                                    "formattedAddress": "Sri Lanka"}]}
        return R()


def test_billed_rows_are_persisted_before_a_crash():
    """The bug that cost 74 paid-for calls: rows held until the loop returns.

    resolve_names must hand every answer to the caller as it arrives, so a
    failure part-way through cannot discard what has already been paid for.
    """
    saved = []
    fetcher = _FakeFetcher(fail_after=2)
    P.resolve_names(fetcher, "key", ["A", "B", "C"], verbose=False,
                    on_batch=lambda batch: saved.extend(batch), flush_every=100)
    names = [r["destination"] for r in saved]
    assert names == ["A", "B", "C"], \
        "answers already billed for were not handed to the caller"
    assert saved[2]["status"].startswith("ERROR_"), "the failure was not recorded"


def test_a_fatal_status_still_persists_what_was_paid_for():
    """REQUEST_DENIED halfway through must not throw away the first half."""
    class Denied(object):
        """Answers the first two names, then reports the API is not enabled."""

        def __init__(self):
            self.n = 0

        def post_json(self, url, body, headers=None, timeout=20):
            self.n += 1
            denied = self.n > 2

            class R(object):
                @staticmethod
                def json():
                    if denied:
                        return {"error": {"status": "PERMISSION_DENIED",
                                          "message": "not enabled"}}
                    return {"places": [{"id": "ChIJ_x",
                                        "displayName": {"text": "Somewhere"},
                                        "formattedAddress": "Sri Lanka"}]}
            return R()

    saved = []
    try:
        P.resolve_names(Denied(), "key", ["A", "B", "C"], verbose=False,
                        on_batch=lambda b: saved.extend(b), flush_every=100)
    except RuntimeError:
        pass
    else:
        raise AssertionError("a fatal status must stop the run")

    # All three are kept: the two that succeeded, and the one that proved the
    # run had to stop. None of them is re-billed on the next attempt.
    assert [r["destination"] for r in saved] == ["A", "B", "C"]
    assert saved[2]["status"] == "PERMISSION_DENIED"


def test_unprintable_names_do_not_crash_the_run():
    """The corpus carries mojibake; cp1252 stdout must not kill a billed run."""
    assert P._ascii("The Eagle�s View Point") == "The Eagle?s View Point"
    saved = []
    P.resolve_names(_FakeFetcher(fail_after=99), "key",
                    ["Caf� — Point"], verbose=True,
                    on_batch=lambda b: saved.extend(b))
    assert len(saved) == 1


def test_failures_are_retried_but_answers_are_not(tmp_path):
    """A crashed run must be resumable; an answered one must stay free."""
    cache = pd.DataFrame([
        {"destination": "Answered", "place_id": "ChIJ_a", "matched_name": "A",
         "formatted_address": "", "status": "OK", "resolved_on": "2026-08-25"},
        {"destination": "Nothing there", "place_id": "", "matched_name": "",
         "formatted_address": "", "status": "ZERO_RESULTS",
         "resolved_on": "2026-08-25"},
        {"destination": "Denied", "place_id": "", "matched_name": "",
         "formatted_address": "", "status": "PERMISSION_DENIED",
         "resolved_on": "2026-08-25"},
        {"destination": "Timed out", "place_id": "", "matched_name": "",
         "formatted_address": "", "status": "ERROR_ReadTimeout",
         "resolved_on": "2026-08-25"},
    ])
    todo = P.unresolved(["Answered", "Nothing there", "Denied", "Timed out"],
                        cache)
    assert todo == ["Denied", "Timed out"], \
        "a failure was cached as though Google had answered it"


def test_a_retry_replaces_the_failed_row(tmp_path):
    """Retrying must not leave two rows for one destination."""
    path = tmp_path / "place_ids.csv"
    failed = pd.DataFrame([
        {"destination": "Ella Rock", "place_id": "", "matched_name": "",
         "formatted_address": "", "status": "ERROR_ReadTimeout",
         "resolved_on": "2026-08-25"}])
    retried = pd.DataFrame([
        {"destination": "Ella Rock", "place_id": "ChIJ_e",
         "matched_name": "Ella Rock", "formatted_address": "Badulla",
         "status": "OK", "resolved_on": "2026-08-26"}])
    P.save_cache(pd.concat([failed, retried], ignore_index=True), path=path)

    out = P.load_cache(path)
    assert len(out) == 1
    assert out.iloc[0]["status"] == "OK"
    assert out.iloc[0]["place_id"] == "ChIJ_e"


class _QuotaFetcher:
    """Exhausts each key after `per_key` answers, like a daily cap."""

    def __init__(self, per_key):
        self.per_key = per_key
        self.by_key = {}
        self.n = 0

    def post_json(self, url, body, headers=None, timeout=20):
        self.n += 1
        k = headers["X-Goog-Api-Key"]
        self.by_key[k] = self.by_key.get(k, 0) + 1
        spent = self.by_key[k] > self.per_key

        class R(object):
            @staticmethod
            def json():
                if spent:
                    return {"error": {"status": "RESOURCE_EXHAUSTED",
                                      "message": "per day"}}
                return {"places": [{"id": "ChIJ_" + str(len(k)),
                                    "displayName": {"text": "Somewhere"},
                                    "formattedAddress": "Sri Lanka"}]}
        return R()


def test_a_spent_key_hands_off_without_losing_the_destination():
    """The name that hit the quota wall must be retried, not consumed."""
    saved = []
    rows = P.resolve_names(_QuotaFetcher(per_key=2), ["AIzaKEY1", "AIzaKEY22"],
                           ["A", "B", "C", "D"], verbose=False,
                           on_batch=lambda b: saved.extend(b), flush_every=100)
    assert [r["destination"] for r in rows] == ["A", "B", "C", "D"]
    assert all(r["status"] == "OK" for r in rows), \
        "a destination was lost to the key rotation"
    assert [r["destination"] for r in saved] == ["A", "B", "C", "D"]


def test_the_answering_key_is_recorded_but_never_its_value():
    """Provenance for a corpus built across projects, without leaking secrets."""
    rows = P.resolve_names(_QuotaFetcher(per_key=2), ["AIzaKEY1", "AIzaKEY22"],
                           ["A", "B", "C"], verbose=False)
    assert rows[0]["key"] == "key 1 of 2"
    assert rows[2]["key"] == "key 2 of 2"
    for r in rows:
        assert "AIza" not in str(r["key"])


def test_exhausting_every_key_stops_the_run():
    """With no key left, the quota wall is fatal again -- not silent."""
    try:
        P.resolve_names(_QuotaFetcher(per_key=1), ["AIzaKEY1"], ["A", "B"],
                        verbose=False)
    except RuntimeError as exc:
        assert "RESOURCE_EXHAUSTED" in str(exc)
    else:
        raise AssertionError("a spent last key must stop the run")


def test_a_single_key_string_still_works():
    """Backwards compatible: callers passing one key are unaffected."""
    rows = P.resolve_names(_QuotaFetcher(per_key=9), "AIzaKEY1", ["A"],
                           verbose=False)
    assert rows[0]["status"] == "OK"


def test_a_neighbouring_match_is_held_back():
    """The real Ravana case: both names resolved to a DIFFERENT nearby fall.

    Both variants share 'ravana', so the shared-word guard passes them. The
    signal that matters is that Google's own name for the place is neither of
    ours, which means the id may not be our place at all.
    """
    cache = pd.DataFrame([
        {"destination": "Ravana Waterfall", "place_id": "ChIJ_kuda",
         "matched_name": "Kuda Ravana Ella waterfall",
         "formatted_address": "Ella", "status": "OK",
         "resolved_on": "2026-08-25", "key": "key 1 of 1"},
        {"destination": "Ravana Ella Falls", "place_id": "ChIJ_kuda",
         "matched_name": "Kuda Ravana Ella waterfall",
         "formatted_address": "Ella", "status": "OK",
         "resolved_on": "2026-08-25", "key": "key 1 of 1"},
    ])
    dests = pd.Series(["Ravana Waterfall"] * 216 + ["Ravana Ella Falls"] * 206)
    g = P.propose_merges(cache, dests)["groups"][0]

    assert g["kind"] == "needs_review"
    assert g["matched_a_variant"] is False
    assert "Kuda Ravana Ella waterfall" in g["reason"]
    assert "Ravana Waterfall" not in P.mapping_from_groups([g])


def test_a_recognised_match_still_merges():
    """The guard must not swallow the ordinary case it was built around."""
    g = _groups()["ChIJjungle"]
    assert g["matched_a_variant"] is True
    assert g["kind"] == "new"
    assert g["reason"] == ""


def test_variants_from_different_districts_are_held_back():
    """The Maritime Museum case: right name, wrong half of the country.

    'Maritime Museum' is filed under Galle and resolved to the Colombo Port
    Maritime Museum. Every name-based guard passed it; only the corpus's own
    district column shows that 204 reviews were about to move cities.
    """
    cache = pd.DataFrame([
        {"destination": "Maritime Museum", "place_id": "ChIJ_col",
         "matched_name": "Colombo Port Maritime Museum",
         "formatted_address": "19 Chaithya Rd, Colombo", "status": "OK",
         "resolved_on": "2026-08-25", "key": "key 1 of 1"},
        {"destination": "Colombo Port Maritime Museum", "place_id": "ChIJ_col",
         "matched_name": "Colombo Port Maritime Museum",
         "formatted_address": "19 Chaithya Rd, Colombo", "status": "OK",
         "resolved_on": "2026-08-25", "key": "key 1 of 1"},
    ])
    dests = pd.Series(["Maritime Museum"] * 204
                      + ["Colombo Port Maritime Museum"] * 26)
    dists = pd.Series(["Galle"] * 204 + ["Colombo"] * 26)

    g = P.propose_merges(cache, dests, districts=dists)["groups"][0]
    assert g["kind"] == "needs_review"
    assert g["districts"] == ["Colombo", "Galle"]
    assert "different districts" in g["reason"]


def test_same_district_still_merges():
    """The district check must only fire on an actual disagreement."""
    dists = pd.Series(["Galle"] * (183 + 222) + ["Matale"] * 400
                      + ["Galle"] * 300 + ["Badulla"] * 50)
    groups = P.propose_merges(CACHE, DESTINATIONS, districts=dists)["groups"]
    jungle = [g for g in groups if g["place_id"] == "ChIJjungle"][0]
    assert jungle["kind"] == "new"


def test_districts_are_optional():
    """Callers without a district column get the old behaviour, not a crash."""
    assert P.propose_merges(CACHE, DESTINATIONS)["groups"]


# --------------------------------------------------------------------------
# Decisions
# --------------------------------------------------------------------------
def _decision_groups():
    return [
        {"place_id": "ChIJ_yes", "kind": "new", "canonical": "Kept Name",
         "variants": ["Kept Name", "Variant B"], "reviews": {"Kept Name": 10,
                                                             "Variant B": 5},
         "reason": ""},
        {"place_id": "ChIJ_no", "kind": "needs_review", "canonical": "Other",
         "variants": ["Other", "Unrelated"], "reviews": {"Other": 9,
                                                         "Unrelated": 4},
         "reason": "held"},
    ]


def test_undecided_groups_block_the_merge():
    """Undecided is not a soft yes."""
    groups = _decision_groups()
    decisions = P.decisions_template(groups)
    mapping, undecided = P.mapping_from_decisions(groups, decisions)
    assert [g["place_id"] for g in undecided] == ["ChIJ_no"]
    assert "Unrelated" not in mapping


def test_keep_apart_is_honoured():
    groups = _decision_groups()
    decisions = P.decisions_template(groups)
    decisions["ChIJ_no"]["decision"] = P.KEEP_APART
    mapping, undecided = P.mapping_from_decisions(groups, decisions)
    assert undecided == []
    assert "Unrelated" not in mapping, "a refused group was merged anyway"
    assert mapping["Variant B"] == "Kept Name"


def test_a_recorded_judgement_survives_a_rerun():
    """Re-resolving must never quietly undo a decision already made."""
    groups = _decision_groups()
    first = P.decisions_template(groups)
    first["ChIJ_no"]["decision"] = P.KEEP_APART
    first["ChIJ_no"]["reason"] = "two different museums"

    second = P.decisions_template(groups, existing=first)
    assert second["ChIJ_no"]["decision"] == P.KEEP_APART
    assert second["ChIJ_no"]["reason"] == "two different museums"


def test_a_decided_canonical_overrides_the_computed_one():
    """The reader's chosen display name wins over the tool's guess."""
    groups = _decision_groups()
    decisions = P.decisions_template(groups)
    decisions["ChIJ_yes"]["canonical"] = "Deliberate Name"
    mapping, _ = P.mapping_from_decisions(groups, decisions)
    assert set(mapping.values()) == {"Deliberate Name"}
