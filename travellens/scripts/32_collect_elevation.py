"""Collect the terrain grid for the 3D map. No API key required.

  python scripts/32_collect_elevation.py

NASA SRTM 30 m elevation (public domain) read through OpenTopoData's free
service: one request per grid row, one second apart, every row cached as it
arrives. Interrupt it and run it again -- it resumes and asks only for what is
missing.

The grid is embedded in the dashboard so the 3D map needs no tile server and
keeps working with no network at all.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travellens import elevation as E  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Collect SRTM elevation grid.")
    ap.add_argument("--max-rows", type=int, default=0,
                    help="stop after this many new rows (0 = all)")
    args = ap.parse_args()

    print("\nLostinSriLanka -- terrain elevation\n" + "=" * 60)
    print("  {}".format(E.SOURCE))
    print("  one request per row, {}s apart, cached as it goes\n".format(E.PAUSE))

    grid = E.collect(max_rows=args.max_rows)

    print()
    if E.is_complete(grid):
        s = E.summarise(grid)
        print("  complete: {} samples".format(s["samples"]))
        print("  highest sample : {} m   (Pidurutalagala is 2,524 m)".format(
            s["max_m"]))
        print("  mean land      : {} m".format(s["mean_land_m"]))
        print("  sea / no-data  : {:.0%} of the grid".format(s["sea_share"]))
        print("\n  wrote {}".format(E.GRID_JSON))
        print("  next: python scripts/08_build_dashboard.py")
    else:
        done = sum(1 for r in grid["z"] if r is not None)
        print("  incomplete: {} of {} rows. Run again to resume.".format(
            done, grid["rows"]))


if __name__ == "__main__":
    main()
