"""
LostinSriLanka -- terrain elevation for the 3D map.

Why the data is baked in rather than streamed
---------------------------------------------
Every 3D mapping library draws terrain from raster-DEM tiles fetched at view
time, which means a tile server, an API key, and a page that is only as
reliable as somebody else's CDN. pipeline.py is explicit that this project
does not accept that trade: "A live service would need a machine kept running,
monitored and paid for, and would be a single point of failure on demo day. A
static rebuild cannot be 'down'."

So the elevation is collected ONCE into a coarse grid and embedded in the
page. The whole country at this resolution is about 30 KB of integers -- less
than one tile request -- and the dashboard keeps working on a laptop with no
network in an exam room.

Source and licence
------------------
NASA SRTM 30 m, which is public domain, read through the public OpenTopoData
service. Attribution is carried in the output file and shown on the map.

Politeness
----------
OpenTopoData's public instance allows 100 locations per call and asks for one
call per second. This does both, caches every row it receives, and resumes
from the cache -- a re-run after an interruption costs only the missing rows.

Run with:  python scripts/32_collect_elevation.py
"""
import json
import os
import time
from typing import Dict, List, Optional

from . import config as C

API = "https://api.opentopodata.org/v1/srtm30m"
GRID_JSON = C.DATA_PROCESSED / "elevation_grid.json"

# Sri Lanka, with a small margin so the coastline is not clipped by the grid.
BBOX = {"lon_min": 79.55, "lon_max": 82.00,
        "lat_min": 5.85, "lat_max": 9.90}

# Grid size. 64x96 is 6,144 samples: fine enough that the central highlands,
# the Knuckles range and the northern plain are all distinguishable, coarse
# enough to embed and to collect in about a minute.
COLS = 64
ROWS = 96

BATCH = 100          # locations per request, the service's maximum
PAUSE = 1.0          # seconds between requests, the service's request

SOURCE = "NASA SRTM 30m (public domain), via OpenTopoData"
LICENCE = "SRTM is public domain. OpenTopoData: https://www.opentopodata.org/"


def cell_centres() -> Dict[str, List[float]]:
    """The lon and lat of every grid column and row."""
    lons = [BBOX["lon_min"] + (BBOX["lon_max"] - BBOX["lon_min"]) * i / (COLS - 1)
            for i in range(COLS)]
    # Row 0 is the NORTH edge, so the grid reads like an image.
    lats = [BBOX["lat_max"] - (BBOX["lat_max"] - BBOX["lat_min"]) * j / (ROWS - 1)
            for j in range(ROWS)]
    return {"lons": lons, "lats": lats}


def load_grid(path=None) -> Optional[Dict]:
    path = path or GRID_JSON
    if not os.path.exists(str(path)):
        return None
    with open(str(path), encoding="utf-8") as fh:
        return json.load(fh)


def save_grid(grid: Dict, path=None) -> str:
    path = path or GRID_JSON
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(str(path), "w", encoding="utf-8") as fh:
        json.dump(grid, fh, separators=(",", ":"))
    return str(path)


def _blank_grid() -> Dict:
    axes = cell_centres()
    return {
        "bbox": BBOX,
        "cols": COLS,
        "rows": ROWS,
        "lons": [round(v, 5) for v in axes["lons"]],
        "lats": [round(v, 5) for v in axes["lats"]],
        # None marks a row not yet collected, so a resumed run knows what to
        # ask for. Sea is 0, which is a real answer and not a gap.
        "z": [None] * ROWS,
        "source": SOURCE,
        "licence": LICENCE,
    }


def collect(verbose: bool = True, max_rows: int = 0) -> Dict:
    """Fill in any rows the cache is missing. Existing rows are never refetched."""
    import requests

    grid = load_grid() or _blank_grid()
    if grid.get("cols") != COLS or grid.get("rows") != ROWS:
        if verbose:
            print("  grid size changed -- starting a fresh grid")
        grid = _blank_grid()

    axes = cell_centres()
    missing = [j for j, row in enumerate(grid["z"]) if row is None]
    todo = missing[:max_rows] if max_rows else missing
    if verbose:
        print("  grid: {}x{} = {} samples".format(COLS, ROWS, COLS * ROWS))
        print("  rows already cached: {} | missing: {}".format(
            ROWS - len(missing), len(missing)))
        if len(todo) != len(missing):
            print("  fetching {} this run (--max-rows)".format(len(todo)))

    # COLS is 64, under the 100-location limit, so one request per row keeps
    # the resume unit and the request unit the same thing.
    for n, j in enumerate(todo):
        lat = axes["lats"][j]
        locs = "|".join("{:.5f},{:.5f}".format(lat, lon) for lon in axes["lons"])
        try:
            r = requests.get(API, params={"locations": locs}, timeout=40)
            if r.status_code != 200:
                if verbose:
                    print("    row {:>3} HTTP {} -- stopping, rerun to resume"
                          .format(j, r.status_code))
                break
            payload = r.json()
            if payload.get("status") != "OK":
                if verbose:
                    print("    row {:>3} {} -- stopping".format(
                        j, payload.get("error", payload.get("status"))))
                break
            grid["z"][j] = [int(round(pt.get("elevation") or 0))
                            for pt in payload["results"]]
            # Written every row: the collection is slow and polite, and losing
            # it to an interruption would mean asking a free service to do the
            # same work twice.
            save_grid(grid)
            if verbose and (n % 12 == 0 or n == len(todo) - 1):
                done = sum(1 for row in grid["z"] if row is not None)
                print("    {}/{} rows".format(done, ROWS))
        except Exception as exc:
            if verbose:
                print("    row {:>3} failed: {} -- stopping, rerun to resume"
                      .format(j, type(exc).__name__))
            break
        time.sleep(PAUSE)

    return grid


def is_complete(grid: Optional[Dict]) -> bool:
    return bool(grid) and all(row is not None for row in grid.get("z", [None]))


def summarise(grid: Dict) -> Dict:
    """Sanity figures. Sri Lanka's highest point is Pidurutalagala, 2,524 m."""
    vals = [v for row in grid["z"] if row for v in row]
    if not vals:
        return {"samples": 0}
    land = [v for v in vals if v > 0]
    return {
        "samples": len(vals),
        "max_m": max(vals),
        "mean_land_m": round(sum(land) / len(land), 1) if land else 0,
        "sea_share": round(1 - len(land) / len(vals), 3),
    }
