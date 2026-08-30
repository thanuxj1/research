"""
Entry point -- build the contributor portal.

Injects the reference data into portal/template.html and writes
portal/index.html: the visitor-facing half of the system, as static and as
self-contained as the dashboard is. The dashboard reads the corpus out; the
portal takes new evidence in.

Plain words, on purpose
-----------------------
The dashboard is read by people who work with this data. The portal is read by
someone on holiday, and every research word in it was a word they had to
decode: "opinion unit", "polarity", "aspect", "F1 0.702", "E_transformer_rules".
So this script carries a second, friendlier name for each category and a
plain-English accuracy sentence, and the template uses only those. The research
vocabulary is unchanged everywhere else -- this is a translation at the edge,
not a renaming of the pipeline.

The accuracy sentence is built from PRECISION rather than F1, because
precision is the number that answers the question a visitor is actually
asking. "When we put this label on a sentence, how often is it right?" is
exactly precision; F1 mixes in recall, which answers a question about the
sentences we missed and cannot be phrased as a confidence in the label on
screen.

Why the accuracy report is a build input
----------------------------------------
Three of the seven categories -- scenery, price_value, crowd -- have no human
labels behind them (see src/travellens/accuracy.py), so the portal says
"we haven't checked this one yet" rather than rendering them identically to
the four that were validated. That is read from
reports/accuracy_all_aspects.json at build time, so it cannot drift: label
three more aspects, re-run scripts/44_accuracy_report.py, rebuild, and the
warnings disappear on their own.

Run: python scripts/45_build_portal.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from travellens import config as C  # noqa: E402

PORTAL = C.ROOT / "portal"

# Where the portal looks for the API unless ?api= says otherwise. Localhost,
# because that is what scripts/41_serve_api.py binds and this file is meant to
# be opened from disk.
DEFAULT_API = "http://127.0.0.1:8778"

# Portal-only names. The canonical labels in config.py are what the research
# and the dashboard use; these are what a visitor sees. "Roads & Access" is a
# category heading, "Getting there and around" is a thing that happened to you.
FRIENDLY = {
    "roads_access": ("Getting there and around",
                     "The road in, parking, signs, buses, how hard the walk was."),
    "facilities":   ("Toilets and facilities",
                     "Toilets, food and drink, seating, shade, bins, ticket desks."),
    "cleanliness":  ("Litter and cleanliness",
                     "Rubbish, plastic, smells, and how well the place is kept."),
    "safety":       ("Safety",
                     "Anything risky: slippery ground, deep water, falls, animals."),
    "price_value":  ("Prices",
                     "Entry fees, parking, food prices, whether it felt worth it."),
    "crowd":        ("Crowds and noise",
                     "How busy it was, queues, noise -- or how peaceful it was."),
    "scenery":      ("Views and nature",
                     "The scenery itself: views, waterfalls, wildlife, sunsets."),
}

EXAMPLE = {
    "destination": "Kandy Lake",
    "district": "Kandy",
    "text": ("The lake is beautiful but the water is filthy and there is "
             "rubbish along the path. The road in was badly broken up and "
             "it was far too crowded to enjoy."),
}


def _escape(payload) -> str:
    """JSON for embedding in a <script> block.

    '<' is escaped so a destination name containing '</script>' cannot
    terminate the host tag, and ensure_ascii keeps the page byte-safe whatever
    encoding it is opened with -- the same two guarantees
    08_build_dashboard.py makes for its payloads.
    """
    return json.dumps(payload, ensure_ascii=True).replace("<", "\\u003c")


def _phrase(labels):
    """A readable list: "a, b and c". Used in prose, so no trailing comma."""
    if not labels:
        return "None of the topics"
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + " and " + labels[-1]


def _plain_accuracy(precision):
    """The accuracy sentence a visitor reads, or None when nobody has checked.

    Rounded to a whole number out of ten and hedged with "about", because the
    underlying figure rests on 15 to 39 human-labelled positives. A decimal
    here would claim a precision the sample does not carry.
    """
    if precision is None:
        return None
    out_of_ten = int(round(float(precision) * 10))
    return "When we say this, we get it right about {} times in 10".format(
        out_of_ten)


def load_accuracy():
    """Per-aspect accuracy, or None where nobody has measured it."""
    path = C.REPORTS / "accuracy_all_aspects.json"
    if not path.exists():
        raise SystemExit(
            "reports/accuracy_all_aspects.json is missing. Run "
            "python scripts/44_accuracy_report.py first -- the portal will not "
            "present a verdict without saying what stands behind it.")
    with open(str(path), encoding="utf-8") as fh:
        raw = json.load(fh)
    return {k: {"f1": v.get("f1"), "precision": v.get("precision"),
                "human_readers": v.get("human_readers")}
            for k, v in (raw.get("aspects") or {}).items()}


def load_baseline():
    """Historical complaint rates per destination, from the built scorecards."""
    path = C.DATA_PROCESSED / "scorecards.csv"
    if not path.exists():
        print("  [warn] no scorecards.csv -- the baseline panel will be empty")
        return {}
    df = pd.read_csv(path)
    out = {}
    for row in df.to_dict("records"):
        dest = str(row["destination"])
        rec = out.setdefault(dest, {
            "district": str(row["district"]),
            "reviews": int(row.get("destination_reviews") or 0),
            "aspects": {},
        })
        n = int(row.get("n_opinions") or 0)
        if not n:
            continue
        rate = row.get("complaint_rate")
        rec["aspects"][str(row["aspect"])] = {
            "n": n,
            "neg": int(row.get("n_negative") or 0),
            "rate": round(float(rate), 4) if pd.notna(rate) else 0.0,
        }
    return {k: v for k, v in out.items() if v["aspects"]}


def load_media():
    """Collected videos and articles, keyed by destination.

    The same relevance and outlet checks 08_build_dashboard.py applies, for the
    same reason: an item whose text does not name the destination is evidence
    of what the search returned, not evidence about the place. Storyboard
    content is displayed and never counted -- see
    tests/test_media_separation.py.
    """
    path = C.DATA_PROCESSED / "media.csv"
    if not path.exists():
        print("  [warn] no media.csv -- the storyboard will show only "
              "visitor stories")
        return {}
    from travellens.media import is_sri_lankan_outlet, supports_destination

    md = pd.read_csv(path).fillna("")
    out, withheld = {}, 0
    for row in md.to_dict("records"):
        blurb = "{} {}".format(row.get("title", ""), row.get("snippet", ""))
        if not supports_destination(row.get("destination", ""), blurb):
            withheld += 1
            continue
        from html import unescape
        item = {
            "kind": row.get("kind", ""),
            "title": unescape(str(row.get("title", ""))),
            "url": row.get("url", ""),
            "source_name": unescape(str(row.get("source_name", ""))),
            "published": str(row.get("published", "")),
            "district": row.get("district", ""),
        }
        if item["kind"] == "news":
            item["local"] = bool(is_sri_lankan_outlet(item["source_name"]))
        out.setdefault(row.get("destination", ""), []).append(item)
    shown = sum(len(v) for v in out.values())
    print("  storyboard: {} of {} collected items, across {} destinations "
          "({} withheld as unsupported)".format(shown, len(md), len(out),
                                                withheld))
    return out


def observation_end():
    """The last day anything in the corpus was collected.

    Printed on the baseline panel so the historical layer is dated rather than
    implied to be current -- the distinction the whole two-layer design rests
    on. Falls back to a plain statement rather than to today's date, because a
    wrong date here reads as a fresher corpus than exists.
    """
    path = C.DATA_PROCESSED / "reviews_clean.csv"
    if not path.exists():
        return "an unrecorded date"
    from travellens.clean import corpus_observation_end
    end = corpus_observation_end(pd.read_csv(path, usecols=["collected_at"]))
    return end or "an unrecorded date"


def main():
    print("\nLostinSriLanka -- contributor portal build\n" + "=" * 60)

    accuracy = load_accuracy()
    aspects = []
    for key, spec in C.ASPECTS.items():
        friendly, blurb = FRIENDLY.get(key, (spec.label, spec.description))
        acc = accuracy.get(key, {})
        aspects.append({
            "key": key,
            "label": friendly,             # what a visitor sees
            "formal_label": spec.label,    # what the research calls it
            "blurb": blurb,
            "f1": acc.get("f1"),
            "precision": acc.get("precision"),
            "human_readers": acc.get("human_readers"),
            "plain_accuracy": _plain_accuracy(acc.get("precision")),
        })

    # "Checked" means somebody measured PRECISION for it -- the number the
    # visitor-facing sentence is built from. F1 is the wrong test here: three
    # aspects are measured by the presence sheet, which yields precision and,
    # honestly, no recall and therefore no F1. Keying on F1 would print "we
    # have not checked this" beside a figure that was checked.
    measured = [a["label"] for a in aspects if a["plain_accuracy"] is not None]
    unmeasured = [a["label"] for a in aspects
                  if a["plain_accuracy"] is None]
    # Two readers and one reader are different claims, and the page has to say
    # which is which. Four aspects were read independently by two people; the
    # other three by one, which yields a figure with nothing to check it
    # against. Collapsing both into "checked" would overstate the weaker half.
    two_readers = [a["label"] for a in aspects
                   if a["plain_accuracy"] is not None
                   and (a["human_readers"] or 0) >= 2]
    one_reader = [a["label"] for a in aspects
                  if a["plain_accuracy"] is not None
                  and (a["human_readers"] or 0) < 2]
    print("  accuracy: {} checked ({} by two readers, {} by one), "
          "{} unchecked ({})".format(
              len(measured), len(two_readers), len(one_reader),
              len(unmeasured), ", ".join(unmeasured) or "none"))

    covered = set(C.DISTRICT_CANON.values()) | {
        "Kandy", "Anuradhapura", "Polonnaruwa", "Kegalle", "Mannar",
        "Trincomalee", "Jaffna",
    }
    districts = [{"name": n, "in_corpus": n in covered} for n in C.DISTRICTS]
    print("  districts: {} ({} with corpus data)".format(
        len(districts), sum(1 for d in districts if d["in_corpus"])))

    baseline = load_baseline()
    cells = sum(len(v["aspects"]) for v in baseline.values())
    print("  baseline: {} destinations, {} destination-aspect cells".format(
        len(baseline), cells))

    media = load_media()

    n_reviews = 0
    reviews_path = C.DATA_PROCESSED / "reviews_clean.csv"
    if reviews_path.exists():
        # One column only. The cleaned corpus carries full review text, and
        # reading all of it to count rows is 40 MB for a number.
        n_reviews = int(len(pd.read_csv(reviews_path, usecols=[0])))

    # Read from the built tree rather than counted here, so the map tab's
    # blurb cannot disagree with the map it introduces.
    n_destinations, n_districts = 0, 0
    tree_path = C.DATA_PROCESSED / "hierarchy.json"
    if tree_path.exists():
        with open(str(tree_path), encoding="utf-8") as fh:
            cov = (json.load(fh).get("coverage") or {})
        n_destinations = int(cov.get("n_destinations") or 0)
        n_districts = int(cov.get("n_districts") or 0)

    obs_end = observation_end()
    print("  corpus: {:,} reviews, {} destinations, {} districts, "
          "observed up to {}".format(n_reviews, n_destinations, n_districts,
                                     obs_end))

    meta = {
        "api_default": DEFAULT_API,
        "max_chars": 5000,
        "observation_end": obs_end,
        "example": EXAMPLE,
        "n_reviews": n_reviews,
    }
    try:
        from travellens.api import MAX_TEXT_CHARS
        meta["max_chars"] = int(MAX_TEXT_CHARS)
    except Exception as exc:                       # fastapi not installed
        print("  [warn] could not read MAX_TEXT_CHARS from api.py ({}); "
              "using {}".format(exc, meta["max_chars"]))

    template = (PORTAL / "template.html").read_text(encoding="utf-8")

    subs = {
        "__ASPECTS__": _escape(aspects),
        "__DISTRICTS__": _escape(districts),
        "__BASELINE__": _escape(baseline),
        "__MEDIA__": _escape(media),
        "__META__": _escape(meta),
        "__MAX_CHARS__": str(meta["max_chars"]),
        "__N_REVIEWS__": "{:,}".format(n_reviews),
        "__N_DESTINATIONS__": "{:,}".format(n_destinations),
        "__N_DISTRICTS__": str(n_districts),
        "__OBS_END__": obs_end,
        "__CHECKED_TWO__": _phrase(two_readers),
        "__CHECKED_ONE__": _phrase(one_reader),
        "__UNCHECKED_SENTENCE__": (
            "" if not unmeasured else
            "{} have not been checked by anyone yet, and we mark them on "
            "screen rather than letting them look as solid as the rest.".format(
                _phrase(unmeasured))),
    }
    for token in subs:
        if token not in template:
            raise SystemExit(
                "portal/template.html has no {} placeholder".format(token))
    for token, value in subs.items():
        template = template.replace(token, value)

    dest = PORTAL / "index.html"
    dest.write_text(template, encoding="utf-8")
    print("  page size: {} KB (self-contained)".format(
        len(template.encode("utf-8")) // 1024))
    print("\nwrote {}".format(dest))
    print("Run it with:  python scripts/50_launch.py   (portal, dashboard "
          "and API on one port)")


if __name__ == "__main__":
    main()
