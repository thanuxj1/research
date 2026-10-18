"""Accuracy for all seven topics, using an AI annotator calibrated against humans.

  python scripts/52_ai_annotated_eval.py

WHAT THIS IS -- and what it is not
  The human gold set covers four topics. Price & value, crowding and scenery had
  precision only. To give every topic precision, recall and F1, Claude (an AI
  assistant, Anthropic) labelled a fresh RANDOM sample of 500 segments for all
  seven topics, blind to the system's tags and verdicts.

  These are AI labels. They are never mixed into the human gold set, never
  reported as human agreement, and carry labelled_by='claude'. Their
  trustworthiness is MEASURED, not assumed: the same annotator also labelled the
  120 Part-A gold rows blind, and its agreement with each human reader is
  reported next to the agreement between the two humans.

Inputs   reports/ai_annotated/random_sample_claude.csv   (500 rows, 7 topics)
         reports/ai_annotated/calibration_claude.csv      (120 rows, 4 topics)
         reports/goldset_focused_annotator{1,2}.csv       (human readers)
         data/processed/segments_scored.csv               (system output)
Output   reports/ai_annotated_eval.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from travellens import config as C  # noqa: E402
from travellens.polarity import aspect_polarity  # noqa: E402

REP = ROOT / "reports"
TOPICS = ["roads_access", "cleanliness", "facilities", "safety", "price_value", "crowd", "scenery"]
GOLD4 = ["roads_access", "cleanliness", "facilities", "safety"]
B = 2000
rng = np.random.default_rng(20261011)


def letter(v):
    v = str(v).strip().upper() if isinstance(v, str) else ""
    return v if v in ("N", "P", "X") else ""


def ci(stat, n):
    vals = []
    for _ in range(B):
        i = rng.integers(0, n, n)
        v = stat(i)
        if v is not None and not np.isnan(v):
            vals.append(v)
    return [round(float(np.percentile(vals, 2.5)), 3), round(float(np.percentile(vals, 97.5)), 3)] if vals else [None, None]


def kappa(a, b):
    a, b = np.asarray(a), np.asarray(b)
    k = cohen_kappa_score(a, b)
    lo_hi = ci(lambda i: cohen_kappa_score(a[i], b[i]) if len(set(a[i]) | set(b[i])) > 1 else None, len(a))
    return {"kappa": round(float(k), 3), "ci95": lo_hi}


def calibration(fname="calibration_claude.csv"):
    c = pd.read_csv(REP / "ai_annotated" / fname, dtype=str)
    h1 = pd.read_csv(REP / "goldset_focused_annotator1.csv", encoding="utf-8-sig", dtype=str)
    h2 = pd.read_csv(REP / "goldset_focused_annotator2.csv", encoding="utf-8-sig", dtype=str)

    def t(df, s):
        x = df[["segment_id"] + GOLD4].copy()
        for a in GOLD4:
            x[a] = x[a].map(letter)
        return x.rename(columns={a: a + s for a in GOLD4})

    m = t(c, "_c").merge(t(h1, "_h1"), on="segment_id").merge(t(h2, "_h2"), on="segment_id", how="left")
    out = {"n_rows": int(len(m)), "topics": {}}
    for a in GOLD4:
        pc, p1, p2 = [(m[a + s] != "").astype(int).values for s in ("_c", "_h1", "_h2")]
        both1 = m[(m[a + "_c"] != "") & (m[a + "_h1"] != "")]
        both2 = m[(m[a + "_c"] != "") & (m[a + "_h2"] != "")]
        bothh = m[(m[a + "_h1"] != "") & (m[a + "_h2"] != "")]
        out["topics"][a] = {
            "presence_kappa_claude_vs_reader1": kappa(pc, p1),
            "presence_kappa_claude_vs_reader2": kappa(pc, p2),
            "presence_kappa_reader1_vs_reader2": kappa(p1, p2),
            "verdict_agreement_claude_vs_reader1": round(float((both1[a + "_c"] == both1[a + "_h1"]).mean()), 3),
            "verdict_n_claude": int(len(both1)),
            "verdict_agreement_claude_vs_reader2": round(float((both2[a + "_c"] == both2[a + "_h2"]).mean()), 3) if len(both2) else None,
            "verdict_n_claude_reader2": int(len(both2)),
            "verdict_agreement_reader1_vs_reader2": round(float((bothh[a + "_h1"] == bothh[a + "_h2"]).mean()), 3),
            "verdict_n_readers": int(len(bothh)),
        }
    return out


def random_sample():
    # Two independent random draws (500 + 300). The deployed lexicon was tuned on
    # neither, so pooling them gives the most precise estimate of the system as it runs.
    lab = pd.concat([pd.read_csv(REP / "ai_annotated" / f, dtype=str)
                     for f in ("random_sample_claude.csv", "holdout_sample_claude.csv")], ignore_index=True)
    cols = ["segment_id", "segment", "pol_final", "pol_lexicon"] + ["asp_" + t for t in TOPICS]
    seg = pd.read_csv(C.DATA_PROCESSED / "segments_scored.csv", usecols=cols)
    m = lab.merge(seg.drop(columns=["segment"]), on="segment_id", how="left")
    tagged = m[["asp_" + t for t in TOPICS]].astype(str).apply(lambda c: c.str.lower().isin(["true", "1"])).any(axis=1)
    # polarity is only computed for segments the system tagged with a topic
    assert m.loc[tagged, "pol_final"].notna().all(), "a tagged sample row has no polarity"
    m["pol_final"] = m["pol_final"].fillna("X")
    m["pol_lexicon"] = m["pol_lexicon"].fillna("X")
    out = {"n_rows": int(len(m)), "topics": {}}
    for t in TOPICS:
        truth = m[t].map(letter)
        human_pos = (truth != "").values
        sys_pos = m["asp_" + t].astype(str).str.lower().isin(["true", "1"]).values
        tp = int((sys_pos & human_pos).sum()); fp = int((sys_pos & ~human_pos).sum()); fn = int((~sys_pos & human_pos).sum())

        def prf(i):
            s, h = sys_pos[i], human_pos[i]
            a, b_, c_ = (s & h).sum(), (s & ~h).sum(), (~s & h).sum()
            p = a / (a + b_) if a + b_ else np.nan
            r = a / (a + c_) if a + c_ else np.nan
            return p, r, (2 * p * r / (p + r) if p and r and not np.isnan(p) and not np.isnan(r) else np.nan)

        p, r, f = prf(np.arange(len(m)))
        # verdict: system per-topic verdict vs the annotator, where both say the topic is present
        sv = np.array([aspect_polarity(sg, t, lb, lx)[0] for sg, lb, lx in zip(m.segment, m.pol_final, m.pol_lexicon)])
        both = sys_pos & human_pos
        vacc = float((sv[both] == truth.values[both]).mean()) if both.sum() else None
        vb = np.where(both)[0]
        out["topics"][t] = {
            "annotated_positives": int(human_pos.sum()), "prevalence": round(float(human_pos.mean()), 3),
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(float(p), 3) if not np.isnan(p) else None,
            "precision_ci95": ci(lambda i: prf(i)[0], len(m)),
            "recall": round(float(r), 3) if not np.isnan(r) else None,
            "recall_ci95": ci(lambda i: prf(i)[1], len(m)),
            "f1": round(float(f), 3) if not np.isnan(f) else None,
            "f1_ci95": ci(lambda i: prf(i)[2], len(m)),
            "verdict_accuracy": round(vacc, 3) if vacc is not None else None,
            "verdict_n": int(both.sum()),
            "verdict_ci95": ci(lambda i: float((sv[vb][i] == truth.values[vb][i]).mean()), len(vb)) if len(vb) else [None, None],
        }
    f1s = [v["f1"] for v in out["topics"].values() if v["f1"] is not None]
    va = [v["verdict_accuracy"] for v in out["topics"].values() if v["verdict_accuracy"] is not None]
    out["macro_f1"] = round(float(np.mean(f1s)), 3)
    out["macro_verdict_accuracy"] = round(float(np.mean(va)), 3)
    return out


def main():
    rep = {
        "what_this_is": "Accuracy for all seven topics from a 500-segment RANDOM sample labelled by Claude (AI), "
                        "blind to system output, plus a calibration of that annotator against the two human readers.",
        "annotator": "Claude (Anthropic), AI assistant. NOT a human reader. labelled_by='claude'.",
        "how_to_read_it": "Trust in these figures rests on the calibration block: where the annotator agrees with each "
                          "human about as well as the humans agree with each other, its labels are a usable substitute "
                          "for that topic; where it agrees less (roads verdict), treat the figure with more caution. "
                          "Intervals are bootstrap 95% (2,000 resamples); topics with few positives have wide intervals.",
        "calibration": calibration(),
        "random_sample": random_sample(),
        # Part B (80 rows sampled where earlier methods disagreed): the hardest cases, not
        # a representative draw, so it is reported beside Part A and never pooled with it.
        # Labelled later, blind to both readers. Computed last so Part A's resamples are unchanged.
        "calibration_part_b": calibration("calibration_partB_claude.csv"),
    }
    (REP / "ai_annotated_eval.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    rs = rep["random_sample"]
    print("RANDOM SAMPLE (n=%d), annotator: Claude" % rs["n_rows"])
    print("%-13s %5s %6s %16s %6s %16s %6s %16s %8s" % ("topic", "pos", "P", "P ci", "R", "R ci", "F1", "F1 ci", "verdict"))
    for t, v in rs["topics"].items():
        print("%-13s %5d %6s %16s %6s %16s %6s %16s %8s" % (t, v["annotated_positives"], v["precision"], v["precision_ci95"],
              v["recall"], v["recall_ci95"], v["f1"], v["f1_ci95"], "%s/%d" % (v["verdict_accuracy"], v["verdict_n"])))
    print("macro F1", rs["macro_f1"], "| macro verdict accuracy", rs["macro_verdict_accuracy"])
    for key, name in (("calibration", "PART A (representative)"), ("calibration_part_b", "PART B (contested)")):
        print("\nCALIBRATION %s n=%d (presence kappa: Claude~R1, Claude~R2, R1~R2 | verdict agree Claude~R1, Claude~R2, R1~R2)"
              % (name, rep[key]["n_rows"]))
        for t, v in rep[key]["topics"].items():
            print("%-13s %s %s %s | %s/%d %s/%d %s/%d" % (t, v["presence_kappa_claude_vs_reader1"]["kappa"], v["presence_kappa_claude_vs_reader2"]["kappa"],
                  v["presence_kappa_reader1_vs_reader2"]["kappa"], v["verdict_agreement_claude_vs_reader1"], v["verdict_n_claude"],
                  v["verdict_agreement_claude_vs_reader2"], v["verdict_n_claude_reader2"],
                  v["verdict_agreement_reader1_vs_reader2"], v["verdict_n_readers"]))


if __name__ == "__main__":
    main()
