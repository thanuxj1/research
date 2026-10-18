"""Shared data loading for the model comparison (scripts 56-58).

Three kinds of evaluation data, kept apart on purpose:

  train        reports/model_dataset/train.csv -- 1,500 AI-annotated sentences
               (+ for the verdict task, the 420 human-labelled supplementary pairs)
  test_random  reports/model_dataset/test_random.csv -- 800 RANDOM AI-annotated
               sentences no model is trained or tuned on
  gold         the human gold set (two independent readers), four topics.
               Part A is representative, Part B is the contested cases.

Everything that chooses a model or a threshold uses `train` only (cross-validation).
"""
from pathlib import Path
from typing import Dict

import pandas as pd

from . import config as C

TOPICS = ["roads_access", "cleanliness", "facilities", "safety", "price_value", "crowd", "scenery"]
GOLD_TOPICS = ["roads_access", "cleanliness", "facilities", "safety"]
LABELS = ["N", "P", "X"]
TOPIC_PHRASE = {
    "roads_access": "roads and access", "cleanliness": "cleanliness", "facilities": "facilities",
    "safety": "safety", "price_value": "price and value", "crowd": "crowding", "scenery": "scenery",
}
DS = C.REPORTS / "model_dataset"
OUT = C.REPORTS / "model_comparison"


def _verdict(v):
    v = str(v).strip().upper() if v is not None and not pd.isna(v) else ""
    return v if v in LABELS else None


def load_train() -> pd.DataFrame:
    d = pd.read_csv(DS / "train.csv", dtype=str).fillna("")
    return d.reset_index(drop=True)


def load_test() -> pd.DataFrame:
    return pd.read_csv(DS / "test_random.csv", dtype=str).fillna("").reset_index(drop=True)


def load_gold() -> pd.DataFrame:
    """One row per gold sentence: segment, part (A/B), and per topic reader 1 / reader 2 verdicts."""
    a1 = pd.read_csv(C.REPORTS / "goldset_focused_annotator1.csv", encoding="utf-8-sig", dtype=str)
    a2 = pd.read_csv(C.REPORTS / "goldset_focused_annotator2.csv", encoding="utf-8-sig", dtype=str)
    a1 = a1[a1["checked"].astype(str).str.strip().str.lower() == "x"]
    a2 = a2.set_index("segment_id")
    rows = []
    for r in a1.to_dict("records"):
        row = {"segment_id": r["segment_id"], "segment": r["segment"],
               "part": "A" if str(r["part"]).startswith("A") else "B"}
        o = a2.loc[r["segment_id"]] if r["segment_id"] in a2.index else None
        for t in GOLD_TOPICS:
            row[t + "_h1"] = _verdict(r.get(t)) or ""
            row[t + "_h2"] = (_verdict(o.get(t)) or "") if o is not None else ""
        rows.append(row)
    return pd.DataFrame(rows)


def presence(df: pd.DataFrame, topics=TOPICS, suffix="") -> pd.DataFrame:
    return pd.DataFrame({t: (df[t + suffix] != "").astype(int).values for t in topics})


def verdict_pairs(df: pd.DataFrame, topics=TOPICS, col_suffix="", source="claude") -> pd.DataFrame:
    rows = []
    for r in df.to_dict("records"):
        for t in topics:
            v = r.get(t + col_suffix, "")
            if v in LABELS:
                rows.append({"segment_id": r["segment_id"], "segment": r["segment"], "topic": t,
                             "label": v, "source": source})
    return pd.DataFrame(rows)


def human_supplementary_pairs() -> pd.DataFrame:
    d = pd.read_csv(C.REPORTS / "LABEL_THESE_polarity.csv", dtype=str)
    d = d[d.verdict.isin(LABELS) & (d.labelled_by == "human")]
    return pd.DataFrame({"segment_id": d.segment_id, "segment": d.segment, "topic": d.aspect,
                         "label": d.verdict, "source": "human"}).reset_index(drop=True)


def verdict_sets() -> Dict[str, pd.DataFrame]:
    """train / test_random / gold_A / gold_B verdict pairs, with no sentence in two sets."""
    train = load_train()
    test = load_test()
    gold = load_gold()
    held_out = set(test.segment_id) | set(gold.segment_id)
    tr = pd.concat([verdict_pairs(train), human_supplementary_pairs()], ignore_index=True)
    tr = tr[~tr.segment_id.isin(held_out)].reset_index(drop=True)
    te = verdict_pairs(test)
    g = []
    for part in ("A", "B"):
        p = verdict_pairs(gold[gold.part == part], GOLD_TOPICS, "_h1", "human")
        h2 = verdict_pairs(gold[gold.part == part], GOLD_TOPICS, "_h2", "human")
        h2 = h2.rename(columns={"label": "label_h2"})[["segment_id", "topic", "label_h2"]]
        p = p.merge(h2, on=["segment_id", "topic"], how="left").fillna({"label_h2": ""})
        p["part"] = part
        g.append(p)
    return {"train": tr, "test_random": te, "gold_A": g[0], "gold_B": g[1]}


def pair_text(topic: str, segment: str) -> str:
    return "%s: %s" % (TOPIC_PHRASE[topic], segment)
