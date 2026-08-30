"""Compare our complaint rates against public Google star ratings.

  python scripts/34_external_validity.py            # collect + correlate
  python scripts/34_external_validity.py --offline  # correlate from cache

Corroboration, not accuracy. Every evaluation label in this project was
produced by the assistant that built it (open problem #1); a star rating was
not. If the destinations we call heavily complained-about also rate poorly
with the public, that is weak independent support for the aggregate. It says
nothing about whether any individual label is right.

One BILLED call per destination, reusing the place_id already cached by
scripts/30_resolve_place_ids.py, so there is no search step. Cached; re-runs
are free.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from travellens import config as C  # noqa: E402
from travellens import external_validity as EV  # noqa: E402
from travellens import place_ids as P  # noqa: E402
from travellens.collect import Fetcher, load_env  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from importlib import import_module  # noqa: E402

usable_keys = import_module("30_resolve_place_ids").usable_keys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--max-requests", type=int, default=400)
    args = ap.parse_args()

    print("\nLostinSriLanka -- external validity\n" + "=" * 60)
    print("  Corroboration against a signal nobody here produced.")

    ids = P.load_cache()
    cache = EV.load_cache()
    todo = EV.outstanding(ids, cache)
    print("  destinations with a place_id : {}".format(
        int((ids["place_id"].astype(str) != "").sum())))
    print("  ratings already cached       : {}".format(
        int((cache["status"] == "OK").sum())))
    print("  to fetch                     : {}".format(len(todo)))

    if todo and not args.offline:
        print("\n  [ratings] Places API (New) -- BILLED, 1 call per destination")
        keys = usable_keys(load_env())
        if keys:
            todo = todo[:args.max_requests]
            f = Fetcher(max_requests=args.max_requests)
            state = {"cache": cache, "saved": 0}

            def flush(batch):
                # Concatenating onto an all-empty frame makes pandas guess
                # dtypes and warn; on the first flush the batch IS the cache.
                add = pd.DataFrame(batch)
                state["cache"] = (add if state["cache"].empty else
                                  pd.concat([state["cache"], add],
                                            ignore_index=True))
                EV.save_cache(state["cache"])
                state["saved"] += len(batch)

            try:
                EV.collect(f, keys, todo, on_batch=flush)
            except RuntimeError as exc:
                print("\n  stopped: {}".format(exc))
            finally:
                cache = state["cache"]
                print("\n  cached {} rows | billed calls: {}".format(
                    state["saved"], f.n))

    sc = pd.read_csv(C.DATA_PROCESSED / "scorecards.csv", encoding="utf-8")
    report = EV.correlate(cache, sc)

    print("\n" + "-" * 60)
    print("  destinations with a public rating: {}".format(
        report["n_destinations_rated"]))
    ov = report.get("overall") or {}
    print("\n  OVERALL complaint rate vs star rating")
    print("    Spearman rho = {}  (n={})  -- negative is the expected direction"
          .format(ov.get("spearman_rate_vs_stars"), ov.get("n")))
    vol = report.get("corpus_vs_public_volume") or {}
    print("\n  our corpus size vs public rating count")
    print("    Spearman rho = {}  (n={})".format(vol.get("spearman"), vol.get("n")))

    print("\n  per aspect:")
    rows = sorted(report["aspects"].items(),
                  key=lambda kv: (kv[1]["spearman_rate_vs_stars"] is None,
                                  kv[1]["spearman_rate_vs_stars"] or 0))
    for aspect, r in rows:
        sig = r.get("significance") or {}
        mark = "" if sig.get("significant_at_05") else "   not significant"
        print("    {:<18} rho = {:<8} (n={:<4} p={}){}".format(
            aspect, str(r["spearman_rate_vs_stars"]), r["n"],
            sig.get("p_value"), mark))

    print("\n  wrote {}".format(EV.save(report)))
    print("\n  Reminder: agreement here is corroboration of the AGGREGATE.")
    print("  Per-label accuracy still needs the human gold set.")


if __name__ == "__main__":
    main()
