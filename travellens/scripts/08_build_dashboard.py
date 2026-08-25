"""
Entry point for Stage 7 -- build the standalone dashboard.

Injects hierarchy.json into dashboard/template.html and writes
dashboard/index.html: a single self-contained file that needs no server,
no internet (beyond the web font), and no build step. Double-click to open.

Run: python scripts/08_build_dashboard.py
"""
import json
import sys
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
    for token in ("__DATA__", "__GEO__", "__MEDIA__", "__LINKS__", "__COORDS__"):
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
        for row in md.to_dict("records"):
            media_by_dest.setdefault(row.get("destination", ""), []).append({
                k: row.get(k, "") for k in
                ("kind", "title", "url", "source_name", "published", "snippet", "aspects")
            })
        print("  storyboard: {} items across {} destinations".format(
            len(md), len(media_by_dest)))
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

    html = (template.replace("__DATA__", payload)
                    .replace("__GEO__", geo_payload)
                    .replace("__MEDIA__", media_payload)
                    .replace("__LINKS__", links_payload)
                    .replace("__COORDS__", coords_payload))

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
