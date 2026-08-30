"""
LostinSriLanka -- Stage 9: fine-tuning a model on the annotated gold set.

THIS is training. Everything before it borrowed a model somebody else trained
on somebody else's data. This script takes a pre-trained language model and
continues its training on YOUR labelled Sri Lankan tourism reviews, so it
learns this domain's meanings rather than a film critic's or a tweeter's.

What it needs
-------------
reports/goldset_annotator1.csv, with the aspect columns filled in using N / P /
X. Until that file has labels this script refuses to run -- there is nothing to
learn from. It is the only stage in the pipeline that cannot be automated,
because the knowledge it transfers is human judgement.

What it produces
----------------
models/travellens-polarity/     the trained model, loadable like any other
reports/finetune_report.json    per-class scores against a held-out test split

Method
------
* Starts from the Twitter-RoBERTa checkpoint (Method D), which already has the
  right 3-class head and the right register. Fine-tuning from it needs far less
  data than starting from a general model -- this matters when the training set
  is a few hundred rows.
* Stratified train/validation/test split, so rare classes appear in all three.
* The TEST split is scored exactly once, at the end. Tuning against it would
  make the reported number meaningless.
* Class weights, because the label distribution is skewed -- without them the
  model can score well by simply never predicting the rare class.

Run with:  python scripts/11_finetune.py
"""
import json
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from . import config as C

GOLD_PATH = C.REPORTS / "goldset_annotator1.csv"
OUTPUT_DIR = C.ROOT / "models" / "travellens-polarity"
BASE_MODEL = "cardiffnlp/twitter-roberta-base-sentiment-latest"

LABELS = ["N", "X", "P"]
LABEL2ID = {l: i for i, l in enumerate(LABELS)}
ID2LABEL = {i: l for l, i in LABEL2ID.items()}

# Below this, a fine-tune will overfit and the score will be noise rather than
# a measurement. 600 rows yielding ~400 labelled segments is workable; 80 is not.
MIN_TRAINING_ROWS = 150


def load_gold() -> pd.DataFrame:
    """Gold sheet -> one row per (segment, aspect) that carries a label.

    A segment labelled for two aspects becomes two training examples. This is
    deliberate: the polarity of "the road is bad but the view is stunning"
    genuinely differs by aspect, and flattening it to one label per segment
    would teach the model to average them.
    """
    if not GOLD_PATH.exists():
        raise SystemExit(
            "\nNo gold set found at {}\n"
            "Run: python scripts/04_build_goldset.py\n".format(GOLD_PATH))

    df = pd.read_csv(GOLD_PATH)
    rows = []
    for r in df.itertuples(index=False):
        for aspect in C.ASPECTS:
            raw = getattr(r, aspect, "")
            label = str(raw).strip().upper()
            if label not in LABEL2ID:
                continue
            rows.append({
                "segment_id": r.segment_id,
                "text": r.segment,
                "aspect": aspect,
                "label": label,
                "destination": r.destination,
            })
    return pd.DataFrame(rows)


def stratified_split(df: pd.DataFrame, seed: int = 42
                     ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """70 / 15 / 15, stratified on the label so rare classes reach every split.

    Splitting is done by SEGMENT, not by row: the same sentence must never
    appear in both training and test, or the test score is inflated by
    memorisation.
    """
    seg_label = df.groupby("segment_id")["label"].agg(
        lambda s: s.value_counts().index[0])
    rng = np.random.RandomState(seed)

    train_ids, val_ids, test_ids = [], [], []
    for label in LABELS:
        ids = seg_label[seg_label == label].index.tolist()
        rng.shuffle(ids)
        n = len(ids)
        n_train, n_val = int(0.70 * n), int(0.15 * n)
        train_ids += ids[:n_train]
        val_ids += ids[n_train:n_train + n_val]
        test_ids += ids[n_train + n_val:]

    pick = lambda ids: df[df["segment_id"].isin(set(ids))].reset_index(drop=True)
    return pick(train_ids), pick(val_ids), pick(test_ids)


def format_input(text: str, aspect: str) -> str:
    """Aspect-aware input.

    The aspect is prepended so one model can answer "how does this visitor feel
    about ROADS in this sentence" separately from "...about SCENERY". This is
    the standard sentence-pair formulation for aspect-based sentiment; without
    it the model cannot give one sentence two different answers.
    """
    return "{}: {}".format(C.ASPECTS[aspect].label, text)


def class_weights(labels: List[str]) -> List[float]:
    counts = pd.Series(labels).value_counts()
    total = len(labels)
    return [total / (len(LABELS) * counts.get(l, 1)) for l in LABELS]


def evaluate(y_true: List[str], y_pred: List[str]) -> Dict:
    """Per-class precision / recall / F1, plus macro-F1 and the confusion matrix.

    Macro-F1 -- not accuracy -- is the headline. Accuracy rewards a model that
    always predicts the majority class; macro-F1 averages across classes, so
    ignoring the rare class is punished.
    """
    out = {"per_class": {}, "support": {}}
    for label in LABELS:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == label and p == label)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != label and p == label)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == label and p != label)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        out["per_class"][label] = {"precision": round(prec, 3),
                                   "recall": round(rec, 3),
                                   "f1": round(f1, 3)}
        out["support"][label] = sum(1 for t in y_true if t == label)

    out["macro_f1"] = round(
        sum(v["f1"] for v in out["per_class"].values()) / len(LABELS), 3)
    out["accuracy"] = round(
        sum(1 for t, p in zip(y_true, y_pred) if t == p) / max(len(y_true), 1), 3)
    out["confusion"] = {
        t: {p: sum(1 for a, b in zip(y_true, y_pred) if a == t and b == p)
            for p in LABELS} for t in LABELS
    }
    return out


def baseline_scores(df: pd.DataFrame) -> Dict:
    """Score the untrained methods on the same test split.

    This is the comparison that gives the fine-tune meaning. "Macro-F1 0.74" on
    its own says nothing; "0.74 against 0.61 for the best untrained method, on
    the same held-out segments" is a result.
    """
    from .polarity import lexicon_polarity

    out = {}
    lex = [lexicon_polarity(t)[0] for t in df["text"]]
    out["A_lexicon"] = evaluate(df["label"].tolist(), lex)

    scored_path = C.DATA_PROCESSED / "segments_scored.csv"
    if scored_path.exists():
        scored = pd.read_csv(scored_path).set_index("segment_id")
        for col, name in (("pol_model", "B_sst2"), ("pol_hybrid", "C_sst2_patched"),
                          ("pol_roberta", "D_roberta"), ("pol_final", "E_deployed")):
            if col not in scored.columns:
                continue
            preds, truth = [], []
            for r in df.itertuples(index=False):
                if r.segment_id in scored.index:
                    v = scored.loc[r.segment_id, col]
                    if isinstance(v, pd.Series):
                        v = v.iloc[0]
                    if pd.notna(v):
                        preds.append(v)
                        truth.append(r.label)
            if preds:
                out[name] = evaluate(truth, preds)
    return out


def load_weak() -> pd.DataFrame:
    """Star-derived weak examples, if any exist. See weak_labels.py.

    Used for a PRE-TRAINING pass only, never for evaluation. weak_labels.py has
    already removed anything overlapping the gold set; this is the second place
    that guarantee is enforced, because a leak here would silently invalidate
    every number in the results chapter.
    """
    path = C.DATA_PROCESSED / "weak_training_set.csv"
    if not path.exists():
        return pd.DataFrame()
    weak = pd.read_csv(path)
    gold_ids = set(pd.read_csv(GOLD_PATH)["segment_id"]) if GOLD_PATH.exists() else set()
    return weak[~weak["segment_id"].isin(gold_ids)].reset_index(drop=True)


# --------------------------------------------------------------------------
# Diagnostic probe.
#
# A fixed set of phrases whose correct tourism reading is not in dispute, used
# to check whether training actually fixed the documented domain failure. This
# is not a substitute for the gold set -- it is 14 hand-picked cases, not a
# representative sample, and it must never be reported as accuracy. But it is
# meaningful without any annotation: if the trained model still calls
# "uncrowded" a complaint, training did not do what it was supposed to.
# --------------------------------------------------------------------------
PROBE = [
    # (text, aspect, expected) -- the domain-inverted cases
    ("This is very calm place to visit", "crowd", "P"),
    ("Very quiet beach, not as touristy as some other areas.", "crowd", "P"),
    ("The place was uncrowded and peaceful", "crowd", "P"),
    ("A slow walk through the tea estate", "roads_access", "P"),
    ("it is very quiet.", "crowd", "P"),
    # genuine complaints -- must NOT be flipped
    ("The road is very bad and full of potholes", "roads_access", "N"),
    ("Dirty, noisy and expensive.", "cleanliness", "N"),
    ("quiet but the toilets are dirty", "facilities", "N"),
    ("but need to clean the pond area", "cleanliness", "N"),
    ("Too risky to go with kids", "safety", "N"),
    # factual statements -- should be neutral
    ("Entrance fee for one local is 150 LKR.", "price_value", "X"),
    ("It is an 8 km walk to the viewpoint", "roads_access", "X"),
    ("The park closes at 2pm", "facilities", "X"),
    ("There is a car park near the entrance", "roads_access", "X"),
]


def run_probe(predict_fn, label: str = "") -> Dict:
    """Score the probe set with any function mapping (text, aspect) -> label."""
    correct, rows = 0, []
    for text, aspect, expected in PROBE:
        got = predict_fn(text, aspect)
        ok = got == expected
        correct += ok
        rows.append({"text": text, "aspect": aspect,
                     "expected": expected, "got": got, "correct": bool(ok)})
    result = {"n": len(PROBE), "correct": correct,
              "score": round(correct / len(PROBE), 3), "rows": rows}
    if label:
        print("\n  probe [{}]: {}/{} correct".format(label, correct, len(PROBE)))
        for r in rows:
            if not r["correct"]:
                print("     MISS  expected {} got {}  |  {}".format(
                    r["expected"], r["got"], r["text"][:58]))
    return result


def train(epochs: int = 4, batch_size: int = 16, lr: float = 2e-5,
          seed: int = 42, use_weak: bool = True) -> Dict:
    import torch
    from torch.utils.data import Dataset
    from transformers import (AutoModelForSequenceClassification, AutoTokenizer,
                              Trainer, TrainingArguments)

    print("\nLostinSriLanka -- Stage 9: fine-tuning\n" + "=" * 60)

    gold = load_gold()
    weak = load_weak() if use_weak else pd.DataFrame()
    weak_only = len(gold) < MIN_TRAINING_ROWS

    if weak_only and len(weak) < MIN_TRAINING_ROWS:
        raise SystemExit(
            "\nNothing to train on.\n"
            "  human-labelled examples : {}\n"
            "  star-derived examples   : {}\n\n"
            "Either label reports/goldset_focused_annotator1.csv, or ingest\n"
            "star-rated reviews and run scripts/12_weak_labels.py.\n".format(
                len(gold), len(weak)))

    if weak_only:
        # ---------------------------------------------------------------
        # WEAK-ONLY MODE.
        #
        # Trains on star-derived labels alone. This produces a genuinely
        # domain-adapted model with no human annotation -- but the evaluation
        # that comes with it is NOT a human-validated accuracy figure:
        #
        #   * train and test labels come from the SAME weak source, so the
        #     score measures agreement with star ratings, not correctness
        #   * stars describe whole reviews; the model is asked about aspects
        #
        # It must therefore be reported as "agreement with star-derived
        # labels", never as accuracy. The qualitative probe below is the more
        # meaningful check until human labels exist.
        # ---------------------------------------------------------------
        print("  MODE: weak-only (no human labels found)")
        print("  star-derived examples : {}".format(len(weak)))
        print("  label counts          : {}".format(weak["label"].value_counts().to_dict()))
        if "tier" in weak.columns:
            print("  by tier               : {}".format(weak["tier"].value_counts().to_dict()))
        print()
        print("  NOTE: the resulting score measures agreement with star ratings,")
        print("        NOT accuracy. Label the gold set to obtain a real one.")
        train_df, val_df, test_df = stratified_split(weak, seed)
        weak = pd.DataFrame()          # already consumed as the training set
    else:
        print("  MODE: gold-supervised")
        print("  labelled examples : {}".format(len(gold)))
        print("  distinct segments : {}".format(gold["segment_id"].nunique()))
        print("  label counts      : {}".format(gold["label"].value_counts().to_dict()))
        print("  per aspect        : {}".format(gold["aspect"].value_counts().to_dict()))
        train_df, val_df, test_df = stratified_split(gold, seed)

    print("\n  split: {} train / {} val / {} test".format(
        len(train_df), len(val_df), len(test_df)))

    tok = AutoTokenizer.from_pretrained(BASE_MODEL)

    class GoldDataset(Dataset):
        def __init__(self, frame):
            self.enc = tok([format_input(t, a) for t, a in
                            zip(frame["text"], frame["aspect"])],
                           truncation=True, max_length=128, padding="max_length")
            self.labels = [LABEL2ID[l] for l in frame["label"]]

        def __len__(self):
            return len(self.labels)

        def __getitem__(self, i):
            item = {k: torch.tensor(v[i]) for k, v in self.enc.items()}
            item["labels"] = torch.tensor(self.labels[i])
            return item

    model = AutoModelForSequenceClassification.from_pretrained(
        BASE_MODEL, num_labels=len(LABELS),
        id2label=ID2LABEL, label2id=LABEL2ID, ignore_mismatched_sizes=True)

    weights = torch.tensor(class_weights(train_df["label"].tolist()),
                           dtype=torch.float)
    print("  class weights     : {}".format(
        {l: round(w, 2) for l, w in zip(LABELS, weights.tolist())}))

    class WeightedTrainer(Trainer):
        def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
            labels = inputs.pop("labels")
            outputs = model(**inputs)
            loss = torch.nn.functional.cross_entropy(
                outputs.logits, labels, weight=weights.to(outputs.logits.device))
            return (loss, outputs) if return_outputs else loss

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    args = TrainingArguments(
        output_dir=str(OUTPUT_DIR / "checkpoints"),
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        learning_rate=lr,
        weight_decay=0.01,
        logging_steps=20,
        save_strategy="no",
        seed=seed,
        report_to=[],
        use_cpu=True,
    )
    # ---- optional stage 1: pre-train on star-derived weak labels ----------
    # Cheap, plentiful, and noisy. Running it first lets the model learn broad
    # sentiment from thousands of examples; the gold pass that follows then
    # only has to teach the precise aspect-level distinctions, which is what
    # the scarce human labels are actually good for.
    # NOTE: `weak` was loaded and, in weak-only mode, emptied above after being
    # consumed as the train/val/test split. Reloading it here would pre-train on
    # the held-out test rows and silently inflate the reported score.
    if len(weak) >= 200:
        print("\n  stage 1/2: pre-training on {} weak (star-derived) examples".format(
            len(weak)))
        print("             these are NOT used for evaluation")
        weak_args = TrainingArguments(
            output_dir=str(OUTPUT_DIR / "checkpoints_weak"),
            num_train_epochs=1, per_device_train_batch_size=batch_size,
            learning_rate=lr, weight_decay=0.01, logging_steps=50,
            save_strategy="no", seed=seed, report_to=[], use_cpu=True)
        WeightedTrainer(model=model, args=weak_args,
                        train_dataset=GoldDataset(weak)).train()
        print("  stage 1 complete\n")
    elif use_weak and not weak_only:
        print("\n  no weak training set (need >=200 examples) -- "
              "training on gold labels only")
        print("  run scripts/12_weak_labels.py after ingesting rated reviews\n")

    stage = "stage 2/2: " if len(weak) >= 200 else ""
    trainer = WeightedTrainer(model=model, args=args,
                              train_dataset=GoldDataset(train_df),
                              eval_dataset=GoldDataset(val_df))
    print("  {}fine-tuning on {} {} examples".format(
        stage, len(train_df),
        "star-derived (weak)" if weak_only else "human-labelled"))
    print("  training on CPU -- expect roughly 10-25 minutes\n")
    trainer.train()

    # ---- the single scoring of the held-out test split --------------------
    preds = trainer.predict(GoldDataset(test_df))
    y_pred = [ID2LABEL[i] for i in preds.predictions.argmax(axis=1)]
    y_true = test_df["label"].tolist()
    trained = evaluate(y_true, y_pred)

    model.save_pretrained(OUTPUT_DIR)
    tok.save_pretrained(OUTPUT_DIR)

    # ---- diagnostic probe: did training fix the domain failure? -----------
    import torch as _torch

    def _predict(text, aspect):
        enc = tok(format_input(text, aspect), truncation=True, max_length=128,
                  return_tensors="pt")
        model.eval()
        with _torch.no_grad():
            logits = model(**enc).logits
        return ID2LABEL[int(logits.argmax(dim=1))]

    probe_after = run_probe(_predict, "trained model")

    # Same probe against the deployed zero-shot method, for comparison.
    from .polarity import (ROBERTA_LABELS, ROBERTA_MODEL, TransformerPolarity,
                           final_polarity, lexicon_polarity)
    _tp = TransformerPolarity(ROBERTA_MODEL, label_map=ROBERTA_LABELS)

    def _predict_zeroshot(text, aspect):
        d = _tp.predict([text], verbose=False)[0]["label"]
        ll, ls = lexicon_polarity(text)
        return final_polarity(text, d, ll, ls)[0]

    probe_before = run_probe(_predict_zeroshot, "zero-shot Method E")

    report = {
        "base_model": BASE_MODEL,
        "epochs": epochs, "batch_size": batch_size, "learning_rate": lr, "seed": seed,
        "weak_pretraining_examples": int(len(weak)) if len(weak) >= 200 else 0,
        "n_train": len(train_df), "n_val": len(val_df), "n_test": len(test_df),
        "mode": "weak_only" if weak_only else "gold_supervised",
        "evaluation_caveat": (
            "Test labels are star-derived, from the same weak source as the "
            "training labels. This score measures AGREEMENT WITH STAR RATINGS, "
            "not accuracy. Report it as such."
        ) if weak_only else None,
        "trained": trained,
        "baselines_on_same_test_split": baseline_scores(test_df),
        "probe_zeroshot": probe_before,
        "probe_trained": probe_after,
        "model_dir": str(OUTPUT_DIR),
    }
    with open(C.REPORTS / "finetune_report.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    print("\n" + "=" * 60)
    print("  {:<20} {:>10} {:>10}".format("method", "macro-F1", "accuracy"))
    print("  " + "-" * 42)
    for name, sc in report["baselines_on_same_test_split"].items():
        print("  {:<20} {:>10} {:>10}".format(name, sc["macro_f1"], sc["accuracy"]))
    print("  {:<20} {:>10} {:>10}   <- trained".format(
        "F_finetuned", trained["macro_f1"], trained["accuracy"]))
    print("\n  per class (trained model)")
    for label in LABELS:
        c = trained["per_class"][label]
        print("    {}  P={:.2f}  R={:.2f}  F1={:.2f}  (n={})".format(
            label, c["precision"], c["recall"], c["f1"], trained["support"][label]))
    print("\n  DIAGNOSTIC PROBE (14 hand-picked cases -- not accuracy)")
    print("    zero-shot Method E : {}/{}".format(
        probe_before["correct"], probe_before["n"]))
    print("    trained model      : {}/{}".format(
        probe_after["correct"], probe_after["n"]))

    if report.get("evaluation_caveat"):
        print("\n  !! {}".format(report["evaluation_caveat"]))

    print("\n  model saved to {}".format(OUTPUT_DIR))
    print("  report saved to {}".format(C.REPORTS / "finetune_report.json"))
    return report


def main():
    train()


if __name__ == "__main__":
    main()
