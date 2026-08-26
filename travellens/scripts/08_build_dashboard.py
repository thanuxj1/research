"""
Entry point for Stage 7 -- build the standalone dashboard.

Injects hierarchy.json into dashboard/template.html and writes
dashboard/index.html: a single self-contained file that needs no server,
no internet (beyond the web font), and no build step. Double-click to open.

Run: python scripts/08_build_dashboard.py
"""
import json
import sys
from html import unescape as html_unescape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travellens import config as C   # noqa: E402

DASHBOARD = C.ROOT / "dashboard"


def main():
    print("\nLostinSriLanka -- Stage 7: dashboard build\n" + "=" * 60)

    tree_path = C.DATA_PROCESSED / "hierarchy.json"
    with open(tree_path, encoding="utf-8") as fh:
        tree = json.load(fh)

    # Escape '<' so the payload can never terminate the host <script> tag,
    # and keep it ASCII-safe so encoding cannot corrupt the page.
    payload = json.dumps(tree, ensure_ascii=True).replace("<", "\\u003c")

    # District boundaries for the choropleth. 22 polygons; only the 12 we have
    # reviews for get coloured -- the rest render hatched as "no data".
    geo_path = C.DATA_RAW / "sri_lanka_districts.geojson"
    with open(geo_path, encoding="utf-8") as fh:
        geo = json.load(fh)
    geo_payload = json.dumps(geo, ensure_ascii=True).replace("<", "\\u003c")

    template = (DASHBOARD / "template.html").read_text(encoding="utf-8")
    for token in ("__DATA__", "__GEO__", "__MEDIA__", "__LINKS__",
                  "__COORDS__", "__TERRAIN__"):
        if token not in template:
            raise SystemExit("template.html has no {} placeholder".format(token))

    # Storyboard media, keyed by destination. Loaded from its OWN file and
    # injected into its OWN slot -- it is never merged into the tree payload,
    # which is what keeps it out of every number on the page.
    media_path = C.DATA_PROCESSED / "media.csv"
    media_by_dest = {}
    if media_path.exists():
        import pandas as pd
        md = pd.read_csv(media_path).fillna("")
        from travellens.media import (is_sri_lankan_outlet,
                                      supports_destination)
        foreign = 0
        withheld = 0
        for row in md.to_dict("records"):
            # Items collected before the relevance check existed are still in
            # the store. They are withheld from the page rather than deleted:
            # the collection is evidence of what the search returned, and a
            # later decision about what to SHOW should not quietly rewrite it.
            blurb = "{} {}".format(row.get("title", ""), row.get("snippet", ""))
            if not supports_destination(row.get("destination", ""), blurb):
                withheld += 1
                continue
            item = {k: row.get(k, "") for k in
                    ("kind", "title", "url", "source_name", "published",
                     "snippet", "aspects")}
            # RSS and the YouTube API deliver titles already HTML-escaped, so
            # "Hike & Camping" arrives as "Hike &amp; Camping". The renderer
            # escapes again on the way out, and the reader sees the entity.
            # Decode once here so exactly one round of escaping happens.
            for field in ("title", "snippet", "source_name"):
                item[field] = html_unescape(str(item[field]))
            # Whether the publisher is recognisably Sri Lankan. Marked on the
            # card rather than filtered out: the page used to claim local
            # sourcing it did not have, and showing the distinction is more
            # honest than either the false claim or a silent deletion.
            if item["kind"] == "news":
                item["local"] = bool(is_sri_lankan_outlet(item["source_name"]))
                if not item["local"]:
                    foreign += 1
            media_by_dest.setdefault(row.get("destination", ""), []).append(item)
        shown = sum(len(v) for v in media_by_dest.values())
        print("  storyboard: {} of {} items shown, across {} destinations".format(
            shown, len(md), len(media_by_dest)))
        print("  withheld: {} item(s) whose text does not bear out the "
              "destination".format(withheld))
        print("  news outlets: {} not recognisably Sri Lankan (marked, not hidden)"
              .format(foreign))
    else:
        print("  storyboard: no media.csv yet -- panel will be empty")
    # Escape '<' as the other payloads do, so a title containing "</script>"
    # cannot terminate the host tag. The replacement must be a RAW string:
    # "<" in a normal literal is the '<' character itself, which would
    # make this a silent no-op.
    media_payload = json.dumps(media_by_dest, ensure_ascii=True).replace("<", "\\u003c")

    # Destination source links. Constructed locally from the place name -- no
    # API call, nothing fetched. See provenance.py for why these are
    # destination-level rather than per-review.
    links_path = C.DATA_PROCESSED / "destination_links.json"
    links = {}
    if links_path.exists():
        with open(links_path, encoding="utf-8") as fh:
            links = json.load(fh)
        print("  source links: {} destinations".format(len(links)))
    links_payload = json.dumps(links, ensure_ascii=True).replace("<", "\\u003c")

    # Destination coordinates from OpenStreetMap (ODbL). Neither review corpus
    # carried latitude or longitude, so this is a partial overlay -- the map
    # legend says as much, since a missing pin must not read as a missing
    # problem.
    coords_path = C.DATA_PROCESSED / "destination_coordinates.csv"
    coords = {}
    if coords_path.exists():
        import pandas as pd
        cd = pd.read_csv(coords_path)
        for r in cd.to_dict("records"):
            coords[r["destination"]] = {"lat": float(r["lat"]), "lon": float(r["lon"])}
        print("  coordinates: {} destinations".format(len(coords)))
    coords_payload = json.dumps(coords, ensure_ascii=True)

    # Terrain for the 3D map. Embedded rather than fetched from a tile server:
    # a mapping library would make the page depend on somebody else's CDN and
    # an API key, and this dashboard has to work on a laptop with no network.
    # Absent grid -> the 3D view falls back to a flat plane, which is what it
    # drew before terrain existed.
    terrain_path = C.DATA_PROCESSED / "elevation_grid.json"
    terrain = {}
    if terrain_path.exists():
        with open(terrain_path, encoding="utf-8") as fh:
            terrain = json.load(fh)
        if any(row is None for row in terrain.get("z", [])):
            print("  terrain: grid incomplete -- run scripts/32_collect_elevation.py")
            terrain = {}
        else:
            print("  terrain: {}x{} elevation grid ({})".format(
                terrain.get("cols"), terrain.get("rows"), terrain.get("source", "")))
    else:
        print("  terrain: none yet -- 3D view will use a flat plane")
    terrain_payload = json.dumps(terrain, separators=(",", ":"))

    html = (template.replace("__DATA__", payload)
                    .replace("__GEO__", geo_payload)
                    .replace("__MEDIA__", media_payload)
                    .replace("__LINKS__", links_payload)
                    .replace("__COORDS__", coords_payload)
                    .replace("__TERRAIN__", terrain_payload))

    have = set(tree["districts"])
    poly = set(f["properties"]["district"] for f in geo["features"])
    print("  map: {} polygons, {} with data, {} hatched as no-data".format(
        len(poly), len(have & poly), len(poly - have)))
    if have - poly:
        print("  WARNING: districts with no polygon: {}".format(sorted(have - poly)))
    out = DASHBOARD / "index.html"
    out.write_text(html, encoding="utf-8")

    kb = out.stat().st_size / 1024
    print("  embedded {} districts / {} destinations".format(
        tree["coverage"]["n_districts"], tree["coverage"]["n_destinations"]))
    print("  page size: {:.0f} KB (self-contained)".format(kb))
    print("\nwrote {}".format(out))


if __name__ == "__main__":
    main()
