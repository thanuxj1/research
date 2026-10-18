"""Turn the labelling batches into the train / test tables the model comparison uses.

  python scripts/55_assemble_model_dataset.py

Reads   reports/model_dataset/to_label_*.csv  (sentences, from 54)
        reports/model_dataset/labels_*.txt    (labels, one line per sentence)
        reports/ai_annotated/random_sample_claude.csv, holdout_sample_claude.csv
Writes  reports/model_dataset/train.csv        1,500 sentences
        reports/model_dataset/test_random.csv  800 random sentences, never trained on
        reports/model_dataset/dataset_summary.json

All labels here are AI annotations (labelled_by=claude). The human gold set is
not touched; it is read separately by the comparison scripts as the final check.
"""
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "reports" / "model_dataset"
AI = ROOT / "reports" / "ai_annotated"
TOPICS = ["roads_access", "cleanliness", "facilities", "safety", "price_value", "crowd", "scenery"]
CODE = {"r": "roads_access", "c": "cleanliness", "f": "facilities", "s": "safety",
        "p": "price_value", "w": "crowd", "v": "scenery"}


def parse(batch: str) -> pd.DataFrame:
    sent = pd.read_csv(D / ("to_label_%s.csv" % batch))
    lines = [l.strip() for l in (D / ("labels_%s.txt" % batch)).read_text(encoding="utf8").splitlines()
             if l.strip() and not l.startswith("#")]
    assert len(lines) == len(sent), (batch, len(lines), len(sent))
    rows = []
    for i, line in enumerate(lines, 1):
        parts = line.split()
        assert int(parts[0]) == i, (batch, i, line)
        lab = {t: "" for t in TOPICS}
        for code in parts[1:]:
            m = re.fullmatch(r"([rcfspwv])([NPX])", code)
            assert m, (batch, i, code)
            lab[CODE[m.group(1)]] = m.group(2)
        rows.append(lab)
    out = pd.concat([sent[["id", "segment_id", "segment"]], pd.DataFrame(rows)], axis=1)
    out["labelled_by"] = "claude"
    out["batch"] = batch
    return out


def old(name: str, batch: str) -> pd.DataFrame:
    d = pd.read_csv(AI / name, dtype=str).fillna("")
    d["batch"] = batch
    return d[["id", "segment_id", "segment"] + TOPICS + ["labelled_by", "batch"]]


def main() -> None:
    train = pd.concat([old("random_sample_claude.csv", "train_random_2026_10_11"),
                       parse("train_random"), parse("train_dense")], ignore_index=True)
    test = pd.concat([old("holdout_sample_claude.csv", "test_random_2026_10_11"),
                      parse("test_random")], ignore_index=True)
    overlap = set(train.segment_id) & set(test.segment_id)
    assert not overlap, "train/test overlap: %d" % len(overlap)
    train.to_csv(D / "train.csv", index=False, encoding="utf-8")
    test.to_csv(D / "test_random.csv", index=False, encoding="utf-8")

    def counts(d):
        return {t: {"mentions": int((d[t] != "").sum()),
                    **{k: int((d[t] == k).sum()) for k in "NPX"}} for t in TOPICS}
    summary = {
        "labelled_by": "claude (AI annotator, calibrated against the human gold set; see ai_annotated_eval.json)",
        "train": {"sentences": len(train), "by_batch": train.batch.value_counts().to_dict(), "topics": counts(train)},
        "test_random": {"sentences": len(test), "by_batch": test.batch.value_counts().to_dict(), "topics": counts(test)},
        "train_test_overlap": 0,
    }
    (D / "dataset_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf8")
    print(json.dumps({k: (v if k != "labelled_by" else None) for k, v in summary.items()}, indent=1)[:2500])


if __name__ == "__main__":
    main()
