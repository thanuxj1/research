"""Nearby-venue tests. Stdlib only, no ML dependencies required:

    python -m unittest discover tests -v

**Nothing here touches the network.** `urlopen` is replaced for the whole module
with a function that fails loudly, so a test that accidentally starts making live
Overpass or Google calls fails instead of quietly depending on the internet (and
on someone else's rate limit). The providers are therefore exercised the way they
are actually risky: query construction and response parsing, against captured
payload shapes.

The behaviour worth pinning hardest is the *honesty* of a result. No POI provider
publishes menus, so a venue's confidence label is the whole basis on which a user
can judge the answer; `TestConfidence` and `TestOrdering` exist because silently
promoting a category guess to a named match would make the feature actively
misleading rather than merely imprecise.
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest import mock

from app import places
from app.config import PlacesSettings
from app.corpus import load_corpus
from app.data.venue_profiles import BAKERY, CAFE, RESTAURANT, profile_for
from app.data.venues_seed import SEED_VENUES, SRI_LANKA_CITIES
from app.places import (
    CONFIDENCE_CATEGORY,
    CONFIDENCE_CUISINE,
    CONFIDENCE_NAMED,
    CONFIDENCE_REASONS,
    GooglePlacesProvider,
    NullProvider,
    OverpassProvider,
    PlacesUnavailable,
    SeedProvider,
    TTLCache,
    Venue,
    VenueFinder,
    build_provider,
    cities,
    coarsen,
    haversine_km,
    infer_tier,
    nearest_city,
    parse_halal,
    resolve_city,
    validate_coordinates,
)
from app.pricing import PriceBook

DATA_PATH = Path(__file__).resolve().parent.parent / "sri_lankan_food_dataset.csv"

COLOMBO = (6.9271, 79.8612)
KANDY = (7.2906, 80.6337)

_urlopen_patch = None


def setUpModule() -> None:
    """Fail loudly on any outbound request from this module's tests."""
    global _urlopen_patch

    def forbidden(*args: object, **kwargs: object):
        raise AssertionError("the test suite must not make network calls")

    _urlopen_patch = mock.patch.object(places.urllib.request, "urlopen", forbidden)
    _urlopen_patch.start()


def tearDownModule() -> None:
    if _urlopen_patch is not None:
        _urlopen_patch.stop()


def venue(name: str, lon_offset: float = 0.0, **kwargs) -> Venue:
    """A venue east of Colombo, for distance ordering without magic numbers."""
    defaults = dict(
        id=f"stub:{name}",
        latitude=COLOMBO[0],
        longitude=COLOMBO[1] + lon_offset,
        kind="restaurant",
        tier="casual",
        source="stub",
    )
    defaults.update(kwargs)
    return Venue(name=name, **defaults)


class StubProvider:
    """Returns a fixed list and records how it was called."""

    name = "stub"
    live = True

    def __init__(self, venues: list[Venue] | None = None, *, ok: bool = True) -> None:
        self.venues = venues or []
        self.ok = ok
        self.calls: list[tuple] = []

    def available(self) -> bool:
        return self.ok

    def search(self, latitude, longitude, radius_km, selectors):
        self.calls.append((latitude, longitude, radius_km, tuple(selectors)))
        return list(self.venues)


class FailingProvider(StubProvider):
    def search(self, latitude, longitude, radius_km, selectors):
        self.calls.append((latitude, longitude, radius_km, tuple(selectors)))
        raise PlacesUnavailable("provider timed out")


# ---------------------------------------------------------------------------
# Geometry and cities
# ---------------------------------------------------------------------------
class TestGeometry(unittest.TestCase):
    def test_distance_to_self_is_zero(self) -> None:
        self.assertEqual(haversine_km(*COLOMBO, *COLOMBO), 0.0)

    def test_known_distance(self) -> None:
        # Colombo to Kandy is about 94 km as the crow flies.
        self.assertAlmostEqual(haversine_km(*COLOMBO, *KANDY), 94.34, places=1)

    def test_symmetric(self) -> None:
        self.assertAlmostEqual(
            haversine_km(*COLOMBO, *KANDY), haversine_km(*KANDY, *COLOMBO), places=9
        )

    def test_antipodal_points_do_not_raise(self) -> None:
        """Floating-point error can push the argument of asin past 1.0, which
        raises instead of returning half the circumference."""
        self.assertAlmostEqual(haversine_km(0.0, 0.0, 0.0, 180.0), 20015.1, places=1)
        self.assertAlmostEqual(haversine_km(90.0, 0.0, -90.0, 0.0), 20015.1, places=1)


class TestCoordinateHandling(unittest.TestCase):
    def test_coarsening_keeps_the_requested_decimals(self) -> None:
        # 3 dp is about 110 m: enough to find a restaurant, not enough to
        # identify a doorstep.
        self.assertEqual(coarsen(6.9271234, 3), 6.927)
        self.assertEqual(coarsen(-79.8612987, 3), -79.861)

    def test_negative_precision_is_clamped_to_whole_degrees(self) -> None:
        self.assertEqual(coarsen(6.9271234, -5), 7.0)

    def test_validate_rejects_impossible_coordinates(self) -> None:
        for latitude, longitude in ((91.0, 0.0), (-91.0, 0.0), (0.0, 181.0), (0.0, -181.0)):
            with self.subTest(latitude=latitude, longitude=longitude):
                with self.assertRaises(ValueError):
                    validate_coordinates(latitude, longitude)

    def test_validate_accepts_the_boundaries(self) -> None:
        self.assertEqual(validate_coordinates(90.0, 180.0), (90.0, 180.0))


class TestCities(unittest.TestCase):
    def test_catalogue_is_served_whole(self) -> None:
        listed = cities()
        self.assertEqual(len(listed), len(SRI_LANKA_CITIES))
        self.assertEqual(
            set(listed[0]), {"name", "latitude", "longitude", "district"}
        )

    def test_nearest_city_labels_a_raw_coordinate(self) -> None:
        name, distance = nearest_city(*COLOMBO)
        self.assertEqual(name, "Colombo")
        self.assertLess(distance, 1.0)

    def test_resolve_is_case_and_whitespace_insensitive(self) -> None:
        for query in ("Kandy", "kandy", "  KANDY  "):
            with self.subTest(query=query):
                self.assertEqual(resolve_city(query)[0], "Kandy")

    def test_unique_prefix_resolves(self) -> None:
        self.assertEqual(resolve_city("Nuwara")[0], "Nuwara Eliya")

    def test_ambiguous_prefix_does_not_guess(self) -> None:
        # "Ka" is both Kalutara and Kandy; picking one would send someone to the
        # wrong end of the island.
        self.assertIsNone(resolve_city("Ka"))

    def test_typos_are_not_fuzzy_matched(self) -> None:
        """Deliberate: an unknown city is an error the caller should surface,
        not something to resolve to the nearest-looking name."""
        self.assertIsNone(resolve_city("Kandi"))
        self.assertIsNone(resolve_city("Atlantis"))

    def test_empty_name_is_none(self) -> None:
        self.assertIsNone(resolve_city("   "))


# ---------------------------------------------------------------------------
# Venue
# ---------------------------------------------------------------------------
class TestVenueLinks(unittest.TestCase):
    def test_surveyed_venue_links_to_the_point(self) -> None:
        url = venue("Green Cabin").map_url
        self.assertIn("openstreetmap.org", url)
        self.assertIn("mlat=6.92710", url)

    def test_approximate_venue_links_to_a_name_search(self) -> None:
        """A wrong pin is worse than one extra tap: seed coordinates are
        neighbourhood-level, so the user's own map app should resolve the name."""
        url = venue("Pilawoos", city="Colombo", approximate=True).map_url
        self.assertIn("google.com/maps/search/", url)
        self.assertIn("Pilawoos%2C+Colombo%2C+Sri+Lanka", url)
        self.assertNotIn("mlat", url)

    def test_directions_for_an_approximate_venue_reuse_the_search(self) -> None:
        approximate = venue("Pilawoos", city="Colombo", approximate=True)
        self.assertEqual(approximate.directions_url, approximate.map_url)

    def test_directions_for_a_surveyed_venue_use_the_coordinates(self) -> None:
        url = venue("Green Cabin").directions_url
        self.assertIn("maps/dir/", url)
        self.assertIn("destination=6.92710,79.86120", url)


class TestVenueSerialization(unittest.TestCase):
    def test_distance_is_rounded_for_display(self) -> None:
        payload = venue("X", distance_km=1.23456).as_dict()
        self.assertEqual(payload["distance_km"], 1.23)

    def test_unknown_distance_stays_none(self) -> None:
        self.assertIsNone(venue("X").as_dict()["distance_km"])

    def test_price_estimate_is_absent_rather_than_zero(self) -> None:
        self.assertIsNone(venue("X").as_dict()["price_estimate"])

    def test_price_estimate_carries_its_tier_and_a_caveat(self) -> None:
        payload = venue(
            "X", tier="street", price_low=550, price_high=900, price_display="Rs 550 - 900"
        ).as_dict()
        self.assertEqual(
            payload["price_estimate"],
            {
                "low": 550,
                "high": 900,
                "display": "Rs 550 - 900",
                "tier": "street",
                "estimated": True,
            },
        )

    def test_cuisines_are_a_list_for_json(self) -> None:
        self.assertEqual(venue("X", cuisines=("sri_lankan",)).as_dict()["cuisines"], ["sri_lankan"])

    def test_halal_is_absent_by_default_rather_than_false(self) -> None:
        # The distinction the whole tri-state exists for: a venue nobody has
        # surveyed must not serialise as "not halal".
        payload = venue("X").as_dict()
        self.assertIsNone(payload["halal"])
        self.assertIsNone(payload["halal_label"])
        self.assertIsNone(payload["halal_note"])


class TestHalalTag(unittest.TestCase):
    """`diet:halal` -> the badge, and what the badge is allowed to claim."""

    def test_halal_only_gets_its_own_label(self) -> None:
        halal, label, note = parse_halal("only")
        self.assertIs(halal, True)
        self.assertEqual(label, "Halal only")
        self.assertIn("entirely halal", note)

    def test_halal_yes_says_alongside_rather_than_only(self) -> None:
        # `yes` means halal food is available, not that the kitchen is halal.
        # Sharing a label with `only` would overclaim for every venue tagged
        # this way, which is the whole reason there are two entries.
        halal, label, note = parse_halal("yes")
        self.assertIs(halal, True)
        self.assertEqual(label, "Halal available")
        self.assertIn("alongside", note)
        self.assertNotEqual(label, parse_halal("only")[1])

    def test_every_positive_note_disclaims_certification(self) -> None:
        # The badge is a claim about someone's kitchen sourced from a wiki edit.
        # If this assertion ever fails, the badge has started asserting more than
        # the data supports.
        for value in ("only", "yes"):
            with self.subTest(value=value):
                note = parse_halal(value)[2]
                self.assertIn("not a certification", note)
                self.assertIn("OpenStreetMap", note)

    def test_explicit_no_is_recorded_but_never_labelled(self) -> None:
        halal, label, note = parse_halal("no")
        self.assertIs(halal, False)
        self.assertIsNone(label)
        self.assertIsNone(note)

    def test_limited_stays_unknown_rather_than_becoming_a_badge(self) -> None:
        # Real information that a binary badge cannot carry honestly, so it is
        # left as unknown instead of being rounded up to "halal".
        self.assertEqual(parse_halal("limited"), (None, None, None))

    def test_untagged_and_unparseable_values_are_unknown(self) -> None:
        for raw in (None, "", "   ", "maybe", "YES?", 0, [], {}):
            with self.subTest(raw=raw):
                self.assertEqual(parse_halal(raw), (None, None, None))

    def test_case_and_whitespace_do_not_hide_a_tag(self) -> None:
        self.assertIs(parse_halal("  Only ")[0], True)
        self.assertIs(parse_halal("YES")[0], True)
        self.assertIs(parse_halal(" No ")[0], False)


class TestTierInference(unittest.TestCase):
    def test_hotel_dining_is_not_priced_like_a_kade(self) -> None:
        self.assertEqual(infer_tier("restaurant", {"tourism": "hotel"}), "hotel")
        self.assertEqual(infer_tier("restaurant", {"stars": "4"}), "hotel")

    def test_international_cuisine_reads_as_tourist_facing(self) -> None:
        self.assertEqual(
            infer_tier("restaurant", {"amenity": "restaurant", "cuisine": "italian"}), "tourist"
        )

    def test_venue_class_drives_the_rest(self) -> None:
        cases = {"fast_food": "street", "bakery": "bakery", "cafe": "cafe", "food_court": "canteen"}
        for kind, expected in cases.items():
            with self.subTest(kind=kind):
                self.assertEqual(infer_tier(kind, {}), expected)

    def test_unknown_class_falls_back_to_casual(self) -> None:
        self.assertEqual(infer_tier("nightclub", {}), "casual")


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
class TestTTLCache(unittest.TestCase):
    def test_miss_then_hit(self) -> None:
        cache = TTLCache()
        self.assertIsNone(cache.get(("k",)))
        cache.put(("k",), [venue("A")])
        self.assertEqual(len(cache.get(("k",))), 1)
        self.assertEqual((cache.hits, cache.misses), (1, 1))

    def test_entries_expire(self) -> None:
        cache = TTLCache(ttl_seconds=60)
        with mock.patch.object(places.time, "monotonic", return_value=1000.0):
            cache.put(("k",), [venue("A")])
        with mock.patch.object(places.time, "monotonic", return_value=1061.0):
            self.assertIsNone(cache.get(("k",)))

    def test_zero_ttl_means_no_expiry(self) -> None:
        cache = TTLCache(ttl_seconds=0)
        with mock.patch.object(places.time, "monotonic", return_value=0.0):
            cache.put(("k",), [venue("A")])
        with mock.patch.object(places.time, "monotonic", return_value=10_000.0):
            self.assertIsNotNone(cache.get(("k",)))

    def test_least_recently_used_is_evicted(self) -> None:
        cache = TTLCache(max_size=2)
        cache.put(("a",), [venue("A")])
        cache.put(("b",), [venue("B")])
        cache.get(("a",))  # refreshes a, so b is now the oldest
        cache.put(("c",), [venue("C")])
        self.assertIsNotNone(cache.get(("a",)))
        self.assertIsNone(cache.get(("b",)))

    def test_size_of_zero_is_not_a_cache_that_stores_nothing(self) -> None:
        self.assertEqual(TTLCache(max_size=0).max_size, 1)

    def test_returned_list_is_a_copy(self) -> None:
        """Callers filter and sort what comes back; that must not edit the entry
        the next request will read."""
        cache = TTLCache()
        cache.put(("k",), [venue("A"), venue("B")])
        cache.get(("k",)).clear()
        self.assertEqual(len(cache.get(("k",))), 2)


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------
class TestOverpassQuery(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = OverpassProvider("https://overpass.invalid/api", 8.0, "Tests/1.0")

    def test_queries_nodes_and_ways_for_every_selector(self) -> None:
        # Larger premises are mapped as building outlines, not points.
        query = self.provider.build_query(*COLOMBO, 3.0, [RESTAURANT, BAKERY])
        self.assertIn('node["amenity"="restaurant"]["name"](around:3000,6.9271,79.8612);', query)
        self.assertIn('way["shop"="bakery"]["name"](around:3000,6.9271,79.8612);', query)
        self.assertIn("out body center", query)

    def test_requires_a_name_tag(self) -> None:
        """An unnamed restaurant node cannot be shown to a user, and excluding
        them upstream keeps the response inside Overpass's fair-use limits."""
        query = self.provider.build_query(*COLOMBO, 1.0, [RESTAURANT])
        for line in query.splitlines():
            if line.strip().startswith(("node[", "way[")):
                self.assertIn('["name"]', line)

    def test_radius_has_a_floor(self) -> None:
        self.assertIn("around:50,", self.provider.build_query(*COLOMBO, 0.001, [RESTAURANT]))

    def test_server_timeout_is_bounded(self) -> None:
        short = OverpassProvider("u", 1.0, "UA").build_query(*COLOMBO, 1.0, [RESTAURANT])
        long = OverpassProvider("u", 100.0, "UA").build_query(*COLOMBO, 1.0, [RESTAURANT])
        self.assertIn("[timeout:5]", short)
        self.assertIn("[timeout:60]", long)

    def test_unsafe_selectors_are_dropped(self) -> None:
        """The values come from our own constants, but validating means a future
        edit cannot introduce Overpass QL injection."""
        query = self.provider.build_query(
            *COLOMBO, 1.0, [RESTAURANT, ('amenity"];out;//', "x")]
        )
        self.assertNotIn("out;//", query)
        self.assertIn('"amenity"="restaurant"', query)

    def test_all_selectors_unsafe_is_an_error_not_an_empty_query(self) -> None:
        with self.assertRaises(PlacesUnavailable):
            self.provider.build_query(*COLOMBO, 1.0, [("bad key", "x")])

    def test_unavailable_without_a_url(self) -> None:
        self.assertFalse(OverpassProvider("", 8.0, "UA").available())


class TestOverpassParsing(unittest.TestCase):
    PAYLOAD = {
        "elements": [
            {
                "type": "node",
                "id": 1,
                "lat": 6.9,
                "lon": 79.9,
                "tags": {
                    "name": "Pilawoos",
                    "amenity": "fast_food",
                    "cuisine": "sri_lankan;asian",
                    "addr:housenumber": "417",
                    "addr:street": "Galle Road",
                    "addr:city": "Colombo",
                    "contact:phone": "+94 11 234 5678",
                    "contact:website": "https://example.invalid",
                    "opening_hours": "24/7",
                },
            },
            {
                "type": "way",
                "id": 2,
                "center": {"lat": 7.0, "lon": 80.0},
                "tags": {"name": "Perera & Sons", "shop": "bakery"},
            },
            # Fictional names, deliberately. The two elements above are real
            # Colombo businesses and the fixture only repeats their venue class;
            # attaching an invented `diet:halal` value to a real restaurant would
            # put a fabricated claim about its kitchen into a source file.
            {
                "type": "node",
                "id": 7,
                "lat": 6.91,
                "lon": 79.86,
                "tags": {"name": "Test Kade One", "amenity": "restaurant", "diet:halal": "only"},
            },
            {
                "type": "node",
                "id": 8,
                "lat": 6.92,
                "lon": 79.87,
                "tags": {"name": "Test Kade Two", "amenity": "restaurant", "diet:halal": "no"},
            },
            {"type": "node", "id": 3, "lat": 6.9, "lon": 79.9, "tags": {"amenity": "cafe"}},
            {"type": "node", "id": 4, "tags": {"name": "No coordinates"}},
            {"type": "node", "id": 5, "lat": "north", "lon": 79.9, "tags": {"name": "Bad coords"}},
            {"type": "node", "id": 6, "lat": 6.9, "lon": 79.9, "tags": "not a dict"},
            "not a dict at all",
        ]
    }

    def setUp(self) -> None:
        self.venues = OverpassProvider.parse(self.PAYLOAD)
        self.by_name = {v.name: v for v in self.venues}

    def test_only_usable_elements_survive(self) -> None:
        # Unusable elements are skipped rather than failing the whole response.
        self.assertEqual(
            sorted(self.by_name),
            ["Perera & Sons", "Pilawoos", "Test Kade One", "Test Kade Two"],
        )

    def test_the_halal_tag_survives_the_trip_through_a_payload(self) -> None:
        # parse_halal is unit-tested above; this pins the wiring, which is the
        # part that silently breaks when the Venue constructor grows a field.
        tagged = self.by_name["Test Kade One"]
        self.assertIs(tagged.halal, True)
        self.assertEqual(tagged.halal_label, "Halal only")
        self.assertIn("not a certification", tagged.halal_note)

    def test_a_negative_tag_is_read_but_carries_no_label(self) -> None:
        refused = self.by_name["Test Kade Two"]
        self.assertIs(refused.halal, False)
        self.assertIsNone(refused.halal_label)

    def test_an_untagged_venue_is_unknown_not_negative(self) -> None:
        self.assertIsNone(self.by_name["Perera & Sons"].halal)

    def test_node_coordinates_and_tags(self) -> None:
        pilawoos = self.by_name["Pilawoos"]
        self.assertEqual((pilawoos.latitude, pilawoos.longitude), (6.9, 79.9))
        self.assertEqual(pilawoos.kind, "fast_food")
        self.assertEqual(pilawoos.tier, "street")
        self.assertEqual(pilawoos.cuisines, ("sri_lankan", "asian"))
        self.assertEqual(pilawoos.address, "417 Galle Road")
        self.assertEqual(pilawoos.city, "Colombo")
        self.assertEqual(pilawoos.opening_hours, "24/7")
        self.assertEqual(pilawoos.id, "osm:node/1")

    def test_contact_prefixed_tags_are_read(self) -> None:
        # OSM tags contact details both ways; reading only `phone` loses half.
        pilawoos = self.by_name["Pilawoos"]
        self.assertEqual(pilawoos.phone, "+94 11 234 5678")
        self.assertEqual(pilawoos.website, "https://example.invalid")

    def test_ways_use_their_centre(self) -> None:
        bakery = self.by_name["Perera & Sons"]
        self.assertEqual((bakery.latitude, bakery.longitude), (7.0, 80.0))
        self.assertEqual(bakery.kind, "bakery")
        self.assertEqual(bakery.id, "osm:way/2")

    def test_live_results_are_not_marked_approximate(self) -> None:
        self.assertFalse(any(v.approximate for v in self.venues))
        self.assertTrue(all(v.source == "overpass" for v in self.venues))

    def test_unexpected_payload_is_empty_not_an_exception(self) -> None:
        for payload in ({}, {"elements": None}, {"elements": {}}):
            with self.subTest(payload=payload):
                self.assertEqual(OverpassProvider.parse(payload), [])


class TestGoogleProvider(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = GooglePlacesProvider("https://places.invalid", "key", 8.0, max_results=50)

    def test_unavailable_without_a_key(self) -> None:
        """Misconfiguration must surface as a degraded stage in /health, not as a
        500 at request time."""
        self.assertFalse(GooglePlacesProvider("https://places.invalid", "", 8.0).available())
        self.assertTrue(self.provider.available())

    def test_search_without_a_key_fails_before_any_request(self) -> None:
        keyless = GooglePlacesProvider("https://places.invalid", "", 8.0)
        with self.assertRaises(PlacesUnavailable):
            keyless.search(*COLOMBO, 3.0, [RESTAURANT])

    def test_result_count_is_capped_at_the_api_limit(self) -> None:
        self.assertEqual(self.provider.max_results, 20)
        self.assertEqual(GooglePlacesProvider("u", "k", 8.0, max_results=0).max_results, 1)

    def test_selectors_map_to_included_types(self) -> None:
        body = self.provider.build_body(*COLOMBO, 3.0, [RESTAURANT, BAKERY])
        self.assertEqual(body["includedTypes"], ["bakery", "restaurant"])
        self.assertEqual(body["rankPreference"], "DISTANCE")
        self.assertEqual(body["locationRestriction"]["circle"]["radius"], 3000.0)

    def test_unmappable_selectors_still_produce_a_query(self) -> None:
        body = self.provider.build_body(*COLOMBO, 3.0, [("shop", "hardware")])
        self.assertEqual(body["includedTypes"], ["restaurant"])

    def test_radius_is_clamped_to_the_api_maximum(self) -> None:
        body = self.provider.build_body(*COLOMBO, 999.0, [RESTAURANT])
        self.assertEqual(body["locationRestriction"]["circle"]["radius"], 50_000.0)

    def test_field_mask_covers_every_field_the_parser_reads(self) -> None:
        """The mask is billed and enforced: a field left out of it arrives absent,
        and the parser would silently produce venues with no name."""
        mask = places._GOOGLE_FIELD_MASK
        for field in (
            "places.id", "places.displayName", "places.location", "places.types",
            "places.primaryType", "places.priceLevel", "places.rating",
            "places.userRatingCount", "places.formattedAddress",
            "places.nationalPhoneNumber", "places.websiteUri",
            "places.currentOpeningHours.openNow",
        ):
            with self.subTest(field=field):
                self.assertIn(field, mask)


class TestGoogleParsing(unittest.TestCase):
    PAYLOAD = {
        "places": [
            {
                "id": "abc",
                "displayName": {"text": "Ministry of Crab", "languageCode": "en"},
                "location": {"latitude": 6.9344, "longitude": 79.8428},
                "types": ["restaurant", "seafood_restaurant"],
                "primaryType": "restaurant",
                "priceLevel": "PRICE_LEVEL_VERY_EXPENSIVE",
                "rating": 4.6,
                "userRatingCount": 9000,
                "formattedAddress": "Old Dutch Hospital, Colombo",
                "nationalPhoneNumber": "011 234 2722",
                "websiteUri": "https://example.invalid",
                "currentOpeningHours": {"openNow": True},
            },
            {
                "id": "def",
                "displayName": "Perera & Sons",
                "location": {"latitude": 6.9, "longitude": 79.86},
                "types": ["bakery"],
                "primaryType": "bakery",
            },
            {"id": "ghi", "location": {"latitude": 6.9, "longitude": 79.86}},
            {"id": "jkl", "displayName": {"text": "No location"}},
            {"id": "mno", "displayName": {"text": "Bad location"}, "location": {"latitude": "x"}},
            "not a dict",
        ]
    }

    def setUp(self) -> None:
        self.venues = GooglePlacesProvider.parse(self.PAYLOAD)
        self.by_name = {v.name: v for v in self.venues}

    def test_only_named_and_located_places_survive(self) -> None:
        self.assertEqual(sorted(self.by_name), ["Ministry of Crab", "Perera & Sons"])

    def test_display_name_is_read_in_both_documented_shapes(self) -> None:
        self.assertIn("Ministry of Crab", self.by_name)  # object form
        self.assertIn("Perera & Sons", self.by_name)  # bare string

    def test_price_level_drives_the_tier(self) -> None:
        self.assertEqual(self.by_name["Ministry of Crab"].tier, "hotel")

    def test_missing_price_level_falls_back_to_the_venue_class(self) -> None:
        bakery = self.by_name["Perera & Sons"]
        self.assertEqual(bakery.kind, "bakery")
        self.assertEqual(bakery.tier, "bakery")

    def test_rich_fields_are_carried_through(self) -> None:
        crab = self.by_name["Ministry of Crab"]
        self.assertEqual(crab.rating, 4.6)
        self.assertEqual(crab.rating_count, 9000)
        self.assertIs(crab.open_now, True)
        self.assertEqual(crab.phone, "011 234 2722")
        self.assertEqual(crab.address, "Old Dutch Hospital, Colombo")
        self.assertEqual(crab.id, "google:abc")

    def test_google_never_claims_a_halal_status(self) -> None:
        """Places API (New) has no halal field.

        A `types` value is a venue class, not a dietary claim, so nothing here may
        infer one. Under a Google-backed deployment every venue is halal-unknown
        and the client shows no badges - which is the truth about what this
        provider knows, not a gap to be filled in later by guessing.
        """
        for venue_ in self.venues:
            with self.subTest(venue=venue_.name):
                self.assertIsNone(venue_.halal)
                self.assertIsNone(venue_.halal_label)

    def test_types_stand_in_for_a_cuisine_tag(self) -> None:
        # Google has no cuisine field; `types` is the closest equivalent and
        # feeds the same cuisine matching.
        self.assertIn("seafood_restaurant", self.by_name["Ministry of Crab"].cuisines)

    def test_unexpected_payload_is_empty_not_an_exception(self) -> None:
        for payload in ({}, {"places": None}, {"places": "nope"}):
            with self.subTest(payload=payload):
                self.assertEqual(GooglePlacesProvider.parse(payload), [])


class TestSeedProvider(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = SeedProvider()

    def test_always_available_but_never_live(self) -> None:
        self.assertTrue(self.provider.available())
        self.assertFalse(self.provider.live)

    def test_filters_by_venue_class(self) -> None:
        found = self.provider.search(*COLOMBO, 500.0, [BAKERY])
        self.assertTrue(found)
        self.assertTrue(all(v.kind == "bakery" for v in found))

    def test_filters_by_radius(self) -> None:
        near = self.provider.search(*COLOMBO, 5.0, [RESTAURANT])
        far = self.provider.search(*COLOMBO, 500.0, [RESTAURANT])
        self.assertLess(len(near), len(far))

    def test_every_entry_admits_it_is_approximate(self) -> None:
        """This is what makes the client link to a name search instead of a pin."""
        found = self.provider.search(*COLOMBO, 500.0, [])
        self.assertEqual(len(found), len(SEED_VENUES))
        self.assertTrue(all(v.approximate and v.source == "seed" for v in found))

    def test_ids_are_unique(self) -> None:
        found = self.provider.search(*COLOMBO, 500.0, [])
        self.assertEqual(len({v.id for v in found}), len(found))

    def test_the_seed_list_makes_no_halal_claims(self) -> None:
        """These are real named businesses with no source for a dietary tag.

        The seed list is what a degraded deployment falls back to, so this is
        also the assertion that losing the live provider cannot turn a badge on.
        """
        for found in self.provider.search(*COLOMBO, 500.0, []):
            with self.subTest(venue=found.name):
                self.assertIsNone(found.halal)
                self.assertIsNone(found.halal_label)


class TestProviderSelection(unittest.TestCase):
    def build(self, **overrides) -> object:
        return build_provider(replace(PlacesSettings(), **overrides))

    def test_default_is_keyless_overpass(self) -> None:
        self.assertIsInstance(self.build(), OverpassProvider)

    def test_google_when_asked(self) -> None:
        self.assertIsInstance(self.build(provider="google"), GooglePlacesProvider)

    def test_static_and_seed_both_mean_the_bundled_list(self) -> None:
        for choice in ("static", "seed", "STATIC"):
            with self.subTest(choice=choice):
                self.assertIsInstance(self.build(provider=choice), SeedProvider)

    def test_disabled_stage_reports_unavailable_rather_than_guessing(self) -> None:
        self.assertIsInstance(self.build(enabled=False), NullProvider)
        for choice in ("none", "off", "disabled"):
            with self.subTest(choice=choice):
                self.assertIsInstance(self.build(provider=choice), NullProvider)

    def test_unknown_provider_warns_and_falls_back(self) -> None:
        with self.assertLogs("app.places", level="WARNING") as captured:
            provider = self.build(provider="yelp")
        self.assertIsInstance(provider, OverpassProvider)
        self.assertIn("yelp", captured.output[0])

    def test_null_provider_refuses_rather_than_returning_nothing(self) -> None:
        with self.assertRaises(PlacesUnavailable):
            NullProvider().search()


# ---------------------------------------------------------------------------
# VenueFinder
# ---------------------------------------------------------------------------
class FinderTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus = load_corpus(DATA_PATH)
        cls.price_book = PriceBook(today=date(2025, 6, 1))

    def dish(self, name: str):
        found = self.corpus.get(name)
        self.assertIsNotNone(found, f"missing dish: {name}")
        return found

    def finder(self, provider=None, price_book=None, **overrides) -> VenueFinder:
        return VenueFinder(
            replace(PlacesSettings(), **overrides),
            provider=provider if provider is not None else StubProvider(),
            price_book=price_book,
        )


class TestConfidence(FinderTestCase):
    """No provider publishes menus, so every row has to say why it is listed."""

    def classify(self, sample: Venue, dish: str = "Chicken Kottu") -> tuple[str, str]:
        return VenueFinder._classify(sample, profile_for(self.dish(dish)))

    def test_a_signboard_naming_the_dish_is_the_strongest_evidence(self) -> None:
        confidence, reason = self.classify(venue("Pilawoos Kottu Corner"))
        self.assertEqual(confidence, CONFIDENCE_NAMED)
        self.assertEqual(reason, places.REASON_NAME_MATCH)

    def test_spelling_variants_count(self) -> None:
        # Kottu is signposted kottu, kotthu, koththu and kothu.
        for name in ("Hotel Koththu", "Kotthu Junction", "Kothu House"):
            with self.subTest(name=name):
                self.assertEqual(self.classify(venue(name))[0], CONFIDENCE_NAMED)

    def test_a_curated_note_counts_as_a_named_match(self) -> None:
        """The note is hand-written by us and does describe what the place sells;
        ignoring it would rank the actual kottu institution below seven
        interchangeable restaurants."""
        confidence, reason = self.classify(venue("Hotel De Pilawoos", note="Famous for kottu"))
        self.assertEqual(confidence, CONFIDENCE_NAMED)
        self.assertEqual(reason, places.REASON_NOTE_MATCH)

    def test_a_cuisine_tag_is_weaker_evidence(self) -> None:
        confidence, _ = self.classify(venue("Green Cabin", cuisines=("sri_lankan",)))
        self.assertEqual(confidence, CONFIDENCE_CUISINE)

    def test_bare_venue_class_is_the_weakest(self) -> None:
        confidence, reason = self.classify(venue("Some Diner"))
        self.assertEqual(confidence, CONFIDENCE_CATEGORY)
        self.assertEqual(reason, places.REASON_CATEGORY_MATCH)

    def test_keywords_are_word_boundary_anchored(self) -> None:
        """Substring matching would put "Tea Gardens Instant Loans" against
        Ceylon Tea, and "Steakhouse" against every tea query."""
        self.assertEqual(
            self.classify(venue("Steakhouse Grill"), dish="Ceylon Tea")[0], CONFIDENCE_CATEGORY
        )
        self.assertEqual(
            self.classify(venue("Tea Castle"), dish="Ceylon Tea")[0], CONFIDENCE_NAMED
        )


class TestOrdering(FinderTestCase):
    def setUp(self) -> None:
        self.provider = StubProvider(
            [
                venue("Near Diner", 0.002),
                venue("Mid Cabin", 0.010, cuisines=("sri_lankan",)),
                venue("Far Kottu Kade", 0.020),
            ]
        )
        self.result = self.finder(self.provider).find(self.dish("Chicken Kottu"), *COLOMBO)

    def test_confidence_outranks_distance(self) -> None:
        """The feature answers "where can I eat *this*", not "where can I eat":
        a place listed as serving the dish 2 km away beats a generic restaurant
        200 m away, which may well not sell it at all."""
        self.assertEqual(
            [r["name"] for r in self.result["results"]],
            ["Far Kottu Kade", "Mid Cabin", "Near Diner"],
        )

    def test_distance_decides_within_a_confidence_level(self) -> None:
        provider = StubProvider([venue("Bravo Diner", 0.020), venue("Alpha Diner", 0.002)])
        result = self.finder(provider).find(self.dish("Chicken Kottu"), *COLOMBO)
        self.assertEqual([r["name"] for r in result["results"]], ["Alpha Diner", "Bravo Diner"])

    def test_name_breaks_a_distance_tie(self) -> None:
        # Deterministic ordering: two venues at the same point must not swap
        # between requests.
        provider = StubProvider([venue("Zebra Diner", 0.002), venue("Alpha Diner", 0.002)])
        result = self.finder(provider).find(self.dish("Chicken Kottu"), *COLOMBO)
        self.assertEqual([r["name"] for r in result["results"]], ["Alpha Diner", "Zebra Diner"])

    def test_distances_are_measured_from_the_caller(self) -> None:
        distances = [r["distance_km"] for r in self.result["results"]]
        self.assertEqual(distances, sorted(distances, reverse=True))  # named first, so furthest


class TestFindPayload(FinderTestCase):
    def setUp(self) -> None:
        self.provider = StubProvider([venue("Some Diner", 0.002)])
        self.finder_ = self.finder(self.provider)

    def test_coordinates_are_coarsened_before_use(self) -> None:
        result = self.finder_.find(self.dish("Chicken Kottu"), 6.9271987, 79.8612987)
        self.assertEqual(result["location"]["latitude"], 6.927)
        self.assertEqual(result["location"]["longitude"], 79.861)
        self.assertEqual(result["location"]["coarsened_to_decimals"], 3)

    def test_the_coarsened_position_is_what_reaches_the_provider(self) -> None:
        """Rounding that happens after the upstream call protects nobody."""
        self.finder_.find(self.dish("Chicken Kottu"), 6.9271987, 79.8612987)
        latitude, longitude, _radius, _selectors = self.provider.calls[0]
        self.assertEqual((latitude, longitude), (6.927, 79.861))

    def test_position_is_labelled_with_the_nearest_city(self) -> None:
        result = self.finder_.find(self.dish("Chicken Kottu"), *COLOMBO)
        self.assertEqual(result["location"]["nearest_city"], "Colombo")

    def test_radius_is_clamped_to_the_configured_maximum(self) -> None:
        result = self.finder_.find(self.dish("Chicken Kottu"), *COLOMBO, radius_km=999)
        self.assertEqual(result["radius_km"], PlacesSettings().max_radius_km)

    def test_absurdly_small_radius_still_searches_something(self) -> None:
        result = self.finder_.find(self.dish("Chicken Kottu"), *COLOMBO, radius_km=0.0001)
        self.assertEqual(result["radius_km"], 0.1)

    def test_limit_caps_the_list_but_the_total_is_still_reported(self) -> None:
        provider = StubProvider([venue(f"Diner {i}", 0.001 * i) for i in range(1, 6)])
        result = self.finder(provider).find(self.dish("Chicken Kottu"), *COLOMBO, limit=2)
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["matched_before_limit"], 5)

    def test_venues_outside_the_radius_are_trimmed(self) -> None:
        """The provider searched a circle around a *coarsened* point, so rounding
        can push a result past the radius the user actually asked for."""
        provider = StubProvider([venue("Near", 0.002), venue("Twenty Km East", 0.180)])
        result = self.finder(provider).find(self.dish("Chicken Kottu"), *COLOMBO, radius_km=2.0)
        self.assertEqual([r["name"] for r in result["results"]], ["Near"])

    def test_the_answer_explains_itself(self) -> None:
        result = self.finder_.find(self.dish("Chicken Kottu"), *COLOMBO)
        self.assertEqual(result["dish"], "Chicken Kottu")
        self.assertEqual(result["category"], "Main Meals")
        self.assertIn("amenity=restaurant", result["searched"])
        self.assertIn("kottu", result["keywords"])
        self.assertEqual(result["confidence_legend"], dict(CONFIDENCE_REASONS))
        self.assertEqual(result["provider"], "stub")

    def test_the_disclaimer_travels_with_the_payload(self) -> None:
        """Stated in the response, not only in the docs, because the client
        renders it verbatim rather than hard-coding its own wording."""
        disclaimer = self.finder_.find(self.dish("Chicken Kottu"), *COLOMBO)["disclaimer"]
        self.assertIn("no provider publishes menus", disclaimer)
        self.assertIn("stub", disclaimer)

    def test_accompaniments_say_so_instead_of_listing_restaurants(self) -> None:
        """Lunumiris is not sold on its own; a list of restaurants implies you can
        walk in and order a bowl of it."""
        result = self.finder_.find(self.dish("Lunumiris"), *COLOMBO)
        self.assertTrue(result["accompaniment_only"])
        self.assertIn("rice-and-curry plate", result["note"])

    def test_ordinary_dishes_carry_no_note(self) -> None:
        self.assertIsNone(self.finder_.find(self.dish("Chicken Kottu"), *COLOMBO)["note"])

    def test_impossible_coordinates_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.finder_.find(self.dish("Chicken Kottu"), 91.0, 79.8612)

    def test_the_halal_badge_survives_annotation(self) -> None:
        """`_annotate` rebuilds each venue with `dataclasses.replace`.

        That copies every field it is not overriding, so this passes for free
        today - and fails the moment someone reconstructs a Venue by hand there
        and forgets a field, which is exactly the edit that would drop the badge
        between the parser and the response without breaking anything else.
        """
        provider = StubProvider(
            [venue("Halal Diner", 0.002, halal=True, halal_label="Halal only", halal_note="n")]
        )
        result = self.finder(provider).find(self.dish("Chicken Kottu"), *COLOMBO)
        self.assertIs(result["results"][0]["halal"], True)
        self.assertEqual(result["results"][0]["halal_label"], "Halal only")

    def test_halal_status_does_not_reorder_results(self) -> None:
        """Ranking stays confidence-then-distance.

        Promoting halal venues would quietly turn a factual badge into a dietary
        preference the user never expressed - and would push a nearer, better
        match down the list for everyone who does not care.
        """
        provider = StubProvider(
            [venue("Near Unknown", 0.002), venue("Far Halal", 0.010, halal=True)]
        )
        result = self.finder(provider).find(self.dish("Chicken Kottu"), *COLOMBO)
        self.assertEqual([r["name"] for r in result["results"]], ["Near Unknown", "Far Halal"])


class TestPriceAnnotation(FinderTestCase):
    def test_each_venue_is_priced_for_its_own_tier(self) -> None:
        provider = StubProvider(
            [venue("Kade", 0.002, tier="street"), venue("Hotel", 0.003, tier="hotel")]
        )
        finder = self.finder(provider, price_book=self.price_book)
        results = finder.find(self.dish("Chicken Kottu"), *COLOMBO)["results"]
        by_name = {r["name"]: r["price_estimate"] for r in results}
        price = self.price_book.get("Chicken Kottu")
        self.assertEqual(
            (by_name["Kade"]["low"], by_name["Kade"]["high"]), price.for_tier("street")
        )
        self.assertLess(by_name["Kade"]["high"], by_name["Hotel"]["low"])

    def test_price_estimate_is_marked_as_an_estimate(self) -> None:
        finder = self.finder(StubProvider([venue("Kade", 0.002)]), price_book=self.price_book)
        estimate = finder.find(self.dish("Chicken Kottu"), *COLOMBO)["results"][0]["price_estimate"]
        self.assertIs(estimate["estimated"], True)
        self.assertIn("Rs", estimate["display"])

    def test_no_price_book_means_no_invented_price(self) -> None:
        finder = self.finder(StubProvider([venue("Kade", 0.002)]))
        self.assertIsNone(finder.find(self.dish("Chicken Kottu"), *COLOMBO)["results"][0]["price_estimate"])


class TestCaching(FinderTestCase):
    def test_dishes_sharing_selectors_share_one_upstream_call(self) -> None:
        """All 22 Short Eats must not issue 22 near-identical Overpass requests."""
        provider = StubProvider([venue("Some Diner", 0.002)])
        finder = self.finder(provider)
        finder.find(self.dish("Chicken Kottu"), *COLOMBO)
        finder.find(self.dish("Vegetable Kottu"), *COLOMBO)
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(finder.provider_calls, 1)

    def test_different_venue_classes_are_fetched_separately(self) -> None:
        provider = StubProvider([venue("Some Diner", 0.002)])
        finder = self.finder(provider)
        finder.find(self.dish("Chicken Kottu"), *COLOMBO)  # restaurants
        finder.find(self.dish("Watalappan"), *COLOMBO)  # bakeries, confectioners
        self.assertEqual(len(provider.calls), 2)

    def test_nearby_callers_on_the_same_street_share_a_request(self) -> None:
        # Coarsening is what makes this work: both positions round to 6.927.
        provider = StubProvider([venue("Some Diner", 0.002)])
        finder = self.finder(provider)
        finder.find(self.dish("Chicken Kottu"), 6.92712, 79.86121)
        finder.find(self.dish("Chicken Kottu"), 6.92719, 79.86124)
        self.assertEqual(len(provider.calls), 1)

    def test_failures_are_not_cached(self) -> None:
        """A transient timeout must not pin a degraded result for the whole TTL."""
        provider = FailingProvider()
        finder = self.finder(provider)
        with self.assertLogs("app.places", level="WARNING"):
            finder.find(self.dish("Chicken Kottu"), *COLOMBO)
            finder.find(self.dish("Chicken Kottu"), *COLOMBO)
        self.assertEqual(len(provider.calls), 2)


class TestDegradation(FinderTestCase):
    def test_a_failed_provider_falls_back_to_the_seed_list(self) -> None:
        """An empty list reads as "nothing near you", which is a different and
        wrong answer."""
        finder = self.finder(FailingProvider())
        with self.assertLogs("app.places", level="WARNING"):
            result = finder.find(self.dish("Chicken Kottu"), *COLOMBO, radius_km=25)
        self.assertTrue(result["degraded"])
        self.assertTrue(result["results"])
        self.assertTrue(all(r["source"] == "seed" for r in result["results"]))
        self.assertTrue(all(r["approximate"] for r in result["results"]))
        self.assertEqual(finder.fallbacks, 1)

    def test_the_error_is_reported_rather_than_swallowed(self) -> None:
        finder = self.finder(FailingProvider())
        with self.assertLogs("app.places", level="WARNING"):
            result = finder.find(self.dish("Chicken Kottu"), *COLOMBO)
        self.assertIn("timed out", result["provider_error"])
        self.assertIn("timed out", finder.stats()["last_error"])

    def test_a_healthy_provider_reports_no_error(self) -> None:
        result = self.finder(StubProvider([venue("A", 0.002)])).find(
            self.dish("Chicken Kottu"), *COLOMBO
        )
        self.assertFalse(result["degraded"])
        self.assertIsNone(result["provider_error"])

    def test_coordinates_are_never_logged(self) -> None:
        """The log line deliberately omits the position: an operator debugging a
        provider outage does not need to know where a user was standing."""
        finder = self.finder(FailingProvider())
        with self.assertLogs("app.places", level="WARNING") as captured:
            finder.find(self.dish("Chicken Kottu"), *COLOMBO)
        logged = " ".join(captured.output)
        self.assertNotIn("6.927", logged)
        self.assertNotIn("79.861", logged)

    def test_an_unconfigured_provider_degrades_instead_of_erroring(self) -> None:
        finder = self.finder(StubProvider(ok=False))
        result = finder.find(self.dish("Chicken Kottu"), *COLOMBO, radius_km=25)
        self.assertTrue(result["degraded"])
        self.assertIn("not configured", result["provider_error"])
        self.assertTrue(result["results"])

    def test_seed_fallback_can_be_switched_off(self) -> None:
        finder = self.finder(FailingProvider(), fallback_to_seed=False)
        with self.assertLogs("app.places", level="WARNING"):
            result = finder.find(self.dish("Chicken Kottu"), *COLOMBO)
        self.assertEqual(result["results"], [])
        self.assertTrue(result["degraded"])
        self.assertEqual(finder.fallbacks, 0)

    def test_availability_reflects_the_fallback_setting(self) -> None:
        self.assertTrue(self.finder(NullProvider()).is_available)
        self.assertFalse(self.finder(NullProvider(), fallback_to_seed=False).is_available)

    def test_stats_describe_the_stage_for_health_checks(self) -> None:
        finder = self.finder(StubProvider([venue("A", 0.002)]))
        finder.find(self.dish("Chicken Kottu"), *COLOMBO)
        stats = finder.stats()
        self.assertEqual(stats["provider"], "stub")
        self.assertEqual(stats["provider_calls"], 1)
        self.assertEqual(stats["seed_fallbacks"], 0)
        self.assertEqual(stats["coordinate_precision"], 3)
        self.assertIn("cache", stats)


class TestNearby(FinderTestCase):
    def test_searches_food_venues_broadly(self) -> None:
        provider = StubProvider([venue("A", 0.002)])
        self.finder(provider).nearby(*COLOMBO)
        _lat, _lon, _radius, selectors = provider.calls[0]
        for selector in (RESTAURANT, BAKERY, CAFE):
            with self.subTest(selector=selector):
                self.assertIn(selector, selectors)

    def test_ordered_by_distance_alone(self) -> None:
        # There is no dish, so there is no confidence to rank by.
        provider = StubProvider([venue("Far", 0.020), venue("Near", 0.002)])
        result = self.finder(provider).nearby(*COLOMBO)
        self.assertEqual([r["name"] for r in result["results"]], ["Near", "Far"])

    def test_makes_no_claim_about_any_dish(self) -> None:
        """A dish-free search must not borrow dish-specific evidence wording.

        Previously asserted `reason == ""`, which held for the wrong reason: an
        empty reason left the client rendering a bare "category" confidence badge
        with no tooltip, which reads as a verdict on a dish nobody named. The
        property that matters is that the wording claims nothing about a dish,
        not that it is absent.
        """
        provider = StubProvider([venue("A", 0.002)])
        result = self.finder(provider).nearby(*COLOMBO)
        reason = result["results"][0]["reason"]
        self.assertNotIn("dish", result)
        self.assertTrue(reason)
        for claim in (
            places.REASON_NAME_MATCH,
            places.REASON_NOTE_MATCH,
            places.REASON_CUISINE_MATCH,
            places.REASON_CATEGORY_MATCH,
        ):
            with self.subTest(claim=claim):
                self.assertNotEqual(reason, claim)

    def test_carries_the_same_caveats_as_a_dish_search(self) -> None:
        """The disclaimer was originally on `find()` only, so whether a user saw
        it depended on which endpoint the client happened to call. Same keys on
        both means one component can render either payload."""
        result = self.finder(StubProvider([venue("A", 0.002)])).nearby(*COLOMBO)
        self.assertEqual(result["confidence_legend"], dict(places.CONFIDENCE_REASONS))
        self.assertIn("stub", result["disclaimer"])
        # Worded for a dish-free search: there is no dish to be wrong about.
        self.assertNotIn("the dish", result["disclaimer"])
        self.assertIn("rather than a check of what any of them serves", result["disclaimer"])

    def test_a_dish_search_still_says_it_is_not_a_menu_check(self) -> None:
        result = self.finder(StubProvider([venue("A", 0.002)])).find(
            self.dish("Chicken Kottu"), *COLOMBO
        )
        self.assertIn("no provider publishes menus", result["disclaimer"])
        self.assertIn("not a confirmed sighting of the dish", result["disclaimer"])

    def test_coordinates_are_coarsened_here_too(self) -> None:
        provider = StubProvider([venue("A", 0.002)])
        result = self.finder(provider).nearby(6.9271987, 79.8612987)
        self.assertEqual(result["location"]["latitude"], 6.927)

    def test_explicit_selectors_are_honoured(self) -> None:
        provider = StubProvider([venue("A", 0.002)])
        self.finder(provider).nearby(*COLOMBO, selectors=[BAKERY])
        self.assertEqual(provider.calls[0][3], (BAKERY,))

    def test_impossible_coordinates_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.finder(StubProvider()).nearby(0.0, 181.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
