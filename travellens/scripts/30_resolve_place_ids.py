"""Resolve destination names to Google place_id, then propose merges.

  python scripts/30_resolve_place_ids.py --limit 20     # try 20, cheap
  python scripts/30_resolve_place_ids.py                # all destinations
  python scripts/30_resolve_place_ids.py --offline      # re-read cache, no calls
  python scripts/30_resolve_place_ids.py --decisions    # write the decision file
  python scripts/30_resolve_place_ids.py --apply        # merge the corpus

Needs GOOGLE_MAPS_API_KEY (and optionally _2, _3, ... which are used in turn as
each hits its project's daily quota). One BILLED Places API (New) searchText
call per destination that is not already in data/processed/place_ids.csv, so
re-runs are free.

Merging is never automatic. The normal sequence is:

    --offline --decisions   write one decision slot per proposed merge
    (read reports/place_id_decisions.json, set each to merge/keep_apart)
    --offline --apply       merge exactly what was decided

Once the decisions file exists it is the authority: --apply refuses to touch
the corpus while any group is still 'undecided'. The guards triage; they do
not decide.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from travellens import config as C  # noqa: E402
from travellens import place_ids as P  # noqa: E402
from travellens.collect import Fetcher, load_env  # noqa: E402


def destinations(limit=0):
    """Destination names, busiest first. limit=0 means all of them."""
    df = pd.read_csv(C.CLEAN_REVIEWS_CSV, encoding="utf-8")
    order = df["destination"].value_counts()
    names = [str(n) for n in order.index]
    return names[:limit] if limit else names


def usable_keys(env):
    """Every usable key, in order: GOOGLE_MAPS_API_KEY, then _2, _3, ...

    key_status() only checks that a variable is set, and .env ships with the
    placeholder 'your_google_maps_api_key'. A placeholder that reports as
    'present' then fails with REQUEST_DENIED wastes the reader's afternoon, so
    it is caught here instead.

    More than one key means more than one Google Cloud project, which is a
    deliberate choice about a per-project daily quota rather than an accident
    of configuration. The run says out loud how many it is using.
    """
    names = ["GOOGLE_MAPS_API_KEY"] + [
        "GOOGLE_MAPS_API_KEY_{}".format(i) for i in range(2, 10)]
    keys, rejected = [], []
    for n in names:
        v = env.get(n, "")
        if not v:
            continue
        if v.lower().startswith("your_") or not v.startswith("AIza"):
            rejected.append(n)
            continue
        keys.append(v)
    for n in rejected:
        print("    ignoring {} -- looks like a placeholder, not a key"
              " (real keys begin 'AIza')".format(n))
    if not keys:
        print("    skipped -- no usable key in travellens/.env")
        return []
    if len(keys) > 1:
        print("    {} keys available; each is used until its daily quota"
              " is spent".format(len(keys)))
    return keys


def main():
    ap = argparse.ArgumentParser(
        description="Resolve destinations to Google place_id and propose merges.")
    ap.add_argument("--limit", type=int, default=0,
                    help="destinations to resolve, busiest first (0 = all)")
    ap.add_argument("--max-requests", type=int, default=400,
                    help="hard ceiling on billed calls this run")
    ap.add_argument("--offline", action="store_true",
                    help="use only the cache, make no API calls")
    ap.add_argument("--apply", action="store_true",
                    help="merge the corpus using the proposed groups")
    ap.add_argument("--include-review", action="store_true",
                    help="with --apply, also merge groups flagged needs_review")
    ap.add_argument("--decisions", action="store_true",
                    help="write/refresh reports/place_id_decisions.json, one"
                         " slot per group, keeping answers already recorded")
    args = ap.parse_args()

    print("\nLostinSriLanka -- place_id resolution\n" + "=" * 60)

    names = destinations(args.limit)
    cache = P.load_cache()
    todo = P.unresolved(names, cache)
    print("  destinations       : {}".format(len(names)))
    print("  already resolved   : {}".format(len(names) - len(todo)))
    print("  to resolve         : {}".format(len(todo)))

    if todo and not args.offline:
        print("\n  [places] Places API (New) searchText"
              " -- BILLED, 1 call per destination")
        env = load_env()
        keys = usable_keys(env)
        if keys:
            if len(todo) > args.max_requests:
                print("    capping {} -> {} (--max-requests)".format(
                    len(todo), args.max_requests))
                todo = todo[:args.max_requests]
            print("    {} destinations -> {} billed calls\n".format(
                len(todo), len(todo)))
            f = Fetcher(max_requests=args.max_requests)

            # The callback is the ONLY writer. Every call is billed, so rows
            # are persisted as they arrive rather than held until the loop
            # finishes -- an earlier version lost 74 paid-for answers to a
            # crash in a progress message.
            state = {"cache": cache, "saved": 0}

            def flush(batch):
                state["cache"] = pd.concat(
                    [state["cache"], pd.DataFrame(batch)], ignore_index=True)
                P.save_cache(state["cache"])
                state["saved"] += len(batch)

            try:
                P.resolve_names(f, keys, todo, on_batch=flush)
            except RuntimeError as exc:
                # Credentials, billing, or an API that is not enabled. Whatever
                # was resolved before this point is already on disk.
                print("\n  stopped: {}".format(exc))
            finally:
                cache = state["cache"]
                if state["saved"]:
                    print("\n  cached {} rows -> {}".format(
                        state["saved"], P.CACHE_CSV))
                print("  billed calls this run: {}".format(f.n))
    elif args.offline:
        print("  offline -- no API calls")

    # ---------------------------------------------------------------- report
    df = pd.read_csv(C.CLEAN_REVIEWS_CSV, encoding="utf-8")
    proposal = P.propose_merges(cache, df["destination"],
                                districts=df["district"])
    groups = proposal["groups"]
    kinds = {k: [g for g in groups if g["kind"] == k]
             for k in ("new", "agreed", "needs_review")}

    resolved = int((cache["place_id"].astype(str) != "").sum())
    print("\n" + "-" * 60)
    print("  resolved to a place_id : {} of {}".format(resolved, len(names)))
    print("  merge groups found     : {}".format(len(groups)))
    print("    new (string key missed these) : {}".format(len(kinds["new"])))
    print("    agreed with canonical.py      : {}".format(len(kinds["agreed"])))
    print("    needs review (no shared word) : {}".format(
        len(kinds["needs_review"])))
    print("  string-key merges Google disputes: {}".format(
        len(proposal["conflicts"])))

    for kind, header in (("new", "NEW merges"),
                         ("needs_review", "NEEDS REVIEW -- read before applying")):
        if not kinds[kind]:
            continue
        print("\n  {}:".format(header))
        for g in kinds[kind]:
            total = sum(g["reviews"].values())
            print("    {}  ({} reviews together)  [Google: {}]".format(
                g["canonical"], total, g["matched_name"] or "?"))
            for v in g["variants"]:
                print("      {:<40} {:>6}".format(v[:38], g["reviews"][v]))
            if g.get("reason"):
                print("      why: {}".format(g["reason"]))

    report = {
        "destinations_considered": len(names),
        "resolved": resolved,
        "counts": {k: len(v) for k, v in kinds.items()},
        "groups": groups,
        "conflicts": proposal["conflicts"],
    }
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    with open(P.REPORT_JSON, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, ensure_ascii=False)
    print("\n  wrote {}".format(P.REPORT_JSON))

    # ------------------------------------------------------------- decisions
    if args.decisions:
        tmpl = P.decisions_template(groups, P.load_decisions())
        path = P.save_decisions(tmpl)
        pending = [k for k, v in tmpl.items() if v["decision"] == P.UNDECIDED]
        print("\n  wrote {}".format(path))
        print("  {} groups, {} still undecided".format(len(tmpl), len(pending)))
        if pending:
            print("  edit the file, set each 'decision' to 'merge' or"
                  " 'keep_apart', then re-run with --apply")

    # ----------------------------------------------------------------- apply
    if args.apply:
        recorded = P.load_decisions()
        if recorded:
            # A decisions file, once it exists, is the authority. Falling back
            # to the guards here would let an unanswered group merge itself.
            mapping, undecided = P.mapping_from_decisions(groups, recorded)
            print("\n  --apply: using {} ({} groups decided)".format(
                P.DECISIONS_JSON.name, len(recorded)))
            if undecided:
                print("  REFUSING to merge -- {} group(s) undecided:".format(
                    len(undecided)))
                for g in undecided:
                    print("    {}  ({})".format(g["canonical"], g["place_id"]))
                print("  set each to 'merge' or 'keep_apart' and run again")
                return
        else:
            mapping = P.mapping_from_groups(
                groups, include_review=args.include_review)
        mapping = {v: c for v, c in mapping.items() if v != c}
        if not mapping:
            print("\n  --apply: nothing to merge")
        else:
            print("\n  --apply: merging {} variant names".format(len(mapping)))
            stats = P.apply_mapping(mapping)
            # Coordinates and source links are keyed on the destination NAME,
            # so they have to follow the merge or the map loses pins it had.
            stats["auxiliary"] = P.remap_auxiliary(mapping)
            report["applied"] = stats
            with open(P.REPORT_JSON, "w", encoding="utf-8") as fh:
                json.dump(report, fh, indent=1, ensure_ascii=False)
            print("\n  next: python scripts/10_refresh.py")
    else:
        print("\n  proposal only -- nothing merged.")
        print("  review the report, then re-run with --apply")


if __name__ == "__main__":
    main()
