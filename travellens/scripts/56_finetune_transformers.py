"""Fine-tune transformer models for the model comparison (the slow part; CPU).

  python scripts/56_finetune_transformers.py --task topic   --model roberta
  python scripts/56_finetune_transformers.py --task topic   --model bge
  python scripts/56_finetune_transformers.py --task verdict --model roberta
  python scripts/56_finetune_transformers.py --task verdict --model bge

  topic    7 yes/no outputs per sentence (multi-label), one per topic
  verdict  3 classes (N complaint / P praise / X fact) for a (topic, sentence) pair

Protocol, identical for every model in the comparison
  1. 5-fold cross-validation on the TRAINING set -> out-of-fold scores, used for
     model selection and for choosing decision thresholds.
  2. One final fit on the whole training set -> scores on the untouched random
     test set and on the human gold set.
Hyperparameters are fixed in advance (below), not tuned on any test data.

Writes reports/model_comparison/ft_<task>_<model>.npz (+ .json training log).
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from sklearn.model_selection import KFold, StratifiedKFold

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from travellens import model_data as M  # noqa: E402

MODELS = {
    "roberta": {"name": "cardiffnlp/twitter-roberta-base-sentiment-latest", "lr": 2e-5, "params": "125M"},
    "bge": {"name": "BAAI/bge-small-en-v1.5", "lr": 5e-5, "params": "33M"},
}
EPOCHS, BATCH, MAXLEN, SEED, FOLDS = 4, 16, 96, 42, 5
VERDICT_IDX = {"N": 0, "X": 1, "P": 2}   # the RoBERTa sentiment head is negative / neutral / positive


def build(task, spec):
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(spec["name"])
    if task == "topic":
        model = AutoModelForSequenceClassification.from_pretrained(
            spec["name"], num_labels=len(M.TOPICS), problem_type="multi_label_classification",
            ignore_mismatched_sizes=True)
    else:
        model = AutoModelForSequenceClassification.from_pretrained(
            spec["name"], num_labels=3, ignore_mismatched_sizes=True)
    return tok, model


def encode(tok, texts):
    return tok(list(texts), truncation=True, max_length=MAXLEN, padding=True, return_tensors="pt")


def train_one(task, spec, X, Y, log):
    from transformers import get_linear_schedule_with_warmup
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    tok, model = build(task, spec)
    model.train()
    opt = torch.optim.AdamW(model.parameters(), lr=spec["lr"], weight_decay=0.01)
    steps = EPOCHS * int(np.ceil(len(X) / BATCH))
    sch = get_linear_schedule_with_warmup(opt, int(0.1 * steps), steps)
    if task == "topic":
        pos = Y.sum(0).clip(min=1)
        pw = torch.tensor(np.sqrt((len(Y) - pos) / pos), dtype=torch.float)
        lossf = torch.nn.BCEWithLogitsLoss(pos_weight=pw)
    else:
        lossf = torch.nn.CrossEntropyLoss()
    rng = np.random.default_rng(SEED)
    for ep in range(EPOCHS):
        order = rng.permutation(len(X))
        tot = 0.0
        for i in range(0, len(X), BATCH):
            b = order[i:i + BATCH]
            enc = encode(tok, [X[j] for j in b])
            out = model(**enc).logits
            y = torch.tensor(Y[b], dtype=torch.float if task == "topic" else torch.long)
            loss = lossf(out, y)
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sch.step()
            tot += float(loss) * len(b)
        log.append(round(tot / len(X), 4))
        print("    epoch %d loss %.4f" % (ep + 1, tot / len(X)), flush=True)
    model.eval()
    return tok, model


@torch.no_grad()
def predict(task, tok, model, X):
    out = []
    for i in range(0, len(X), 64):
        logits = model(**encode(tok, X[i:i + 64])).logits
        out.append(torch.sigmoid(logits).numpy() if task == "topic" else torch.softmax(logits, -1).numpy())
    return np.vstack(out)


def data(task):
    if task == "topic":
        tr, te, g = M.load_train(), M.load_test(), M.load_gold()
        return (tr.segment.tolist(), M.presence(tr).values,
                {"test_random": te.segment.tolist(), "gold": g.segment.tolist()})
    s = M.verdict_sets()
    txt = lambda d: [M.pair_text(t, x) for t, x in zip(d.topic, d.segment)]
    return (txt(s["train"]), s["train"].label.map(VERDICT_IDX).values,
            {k: txt(s[k]) for k in ("test_random", "gold_A", "gold_B")})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", choices=["topic", "verdict"], required=True)
    ap.add_argument("--model", choices=list(MODELS), required=True)
    a = ap.parse_args()
    torch.set_num_threads(max(1, (torch.get_num_threads() or 4)))
    spec = MODELS[a.model]
    X, Y, evalsets = data(a.task)
    M.OUT.mkdir(parents=True, exist_ok=True)
    k = Y.shape[1] if a.task == "topic" else 3
    oof = np.zeros((len(X), k))
    folds = (KFold(FOLDS, shuffle=True, random_state=SEED).split(X) if a.task == "topic"
             else StratifiedKFold(FOLDS, shuffle=True, random_state=SEED).split(X, Y))
    logs, t0 = {"cv": []}, time.time()
    for f, (tr, va) in enumerate(folds):
        print("fold %d/%d (%d train, %d validate)" % (f + 1, FOLDS, len(tr), len(va)), flush=True)
        lg = []
        tok, model = train_one(a.task, spec, [X[i] for i in tr], Y[tr], lg)
        oof[va] = predict(a.task, tok, model, [X[i] for i in va])
        logs["cv"].append(lg)
    print("final fit on all %d" % len(X), flush=True)
    lg = []
    t1 = time.time()
    tok, model = train_one(a.task, spec, X, Y, lg)
    fit_s = time.time() - t1
    t2 = time.time()
    scores = {name: predict(a.task, tok, model, xs) for name, xs in evalsets.items()}
    per_item_ms = 1000 * (time.time() - t2) / sum(len(v) for v in evalsets.values())
    logs.update({"final_fit_losses": lg, "model": spec["name"], "params": spec["params"],
                 "epochs": EPOCHS, "batch": BATCH, "lr": spec["lr"], "max_len": MAXLEN, "seed": SEED,
                 "n_train": len(X), "final_fit_seconds": round(fit_s, 1),
                 "inference_ms_per_item_cpu": round(per_item_ms, 2),
                 "total_seconds": round(time.time() - t0, 1)})
    stem = M.OUT / ("ft_%s_%s" % (a.task, a.model))
    np.savez(str(stem) + ".npz", oof=oof, y=Y, **scores)
    Path(str(stem) + ".json").write_text(json.dumps(logs, indent=1), encoding="utf8")
    print("saved", stem, "in %.0f s" % (time.time() - t0))


if __name__ == "__main__":
    main()
