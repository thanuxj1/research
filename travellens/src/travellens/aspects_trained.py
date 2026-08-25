"""
LostinSriLanka -- trained aspect classifier (rules as teacher, model as student).

The architecture this implements
--------------------------------
    RULES  ->  label 57,621 segments  ->  train a classifier  ->  MODEL leads
                                                                  rules fall back

Why this beats both of the earlier attempts
-------------------------------------------
Two things were tried before and both were worse than the plain lexicon:

  * a zero-shot NLI classifier    F1 ~0.3 equivalent, label collapse
  * generic embedding similarity  F1 0.615 vs 0.763 for rules

Neither was TRAINED on this task. They were general-purpose models guessing
from a label name or a description. A classifier fitted to examples of what a
Sri Lankan tourism review about roads actually looks like is a different thing.

Where the training labels come from
-----------------------------------
The rule lexicon. This is distant (weak) supervision: the rules are precise
(0.818 on the evaluation set) but narrow, since they can only find words
somebody wrote down. A model trained on their output learns the concept rather
than the vocabulary, and can then recognise "sewage was running into the
stream" as a cleanliness statement even though no rule mentions sewage.

The known risk, stated plainly
------------------------------
A student cannot be taught what the teacher never knew. If the lexicon
systematically misses an entire kind of phrasing, the model may inherit that
blind spot rather than fix it. Generalisation happens through the sentence
embedding, not by magic, so the gain is real but bounded. Whether it actually
helps is settled by evaluation on the held-out test set, not by assumption.

Design
------
Embed each segment once with MiniLM, then fit one logistic regression per
aspect (one-vs-rest, so a segment can carry several aspects). Chosen over
fine-tuning a transformer because it trains in seconds on CPU rather than
hours, and because the embedding is already computed for the union tagger.

Run with:  python scripts/18_train_aspects.py
"""
import json
import pickle
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from . import config as C
from .aspects_model import EmbeddingAspectTagger

MODEL_PATH = C.ROOT / "models" / "aspect_classifier.pkl"

# Decision threshold per aspect. 0.5 is the natural default for a probability;
# tuned per aspect against the evaluation set in `tune_thresholds`.
DEFAULT_PROB_THRESHOLD = 0.5


class TrainedAspectTagger:
    """One-vs-rest logistic regression over sentence embeddings."""

    def __init__(self, aspects: Optional[List[str]] = None):
        self.aspects = aspects or list(C.ASPECTS)
        self.models: Dict[str, object] = {}
        self.thresholds: Dict[str, float] = {}
        self._embedder = None

    # -- embedding -------------------------------------------------------
    def _embed(self, texts: List[str], verbose: bool = False) -> np.ndarray:
        if self._embedder is None:
            self._embedder = EmbeddingAspectTagger()
            self._embedder._load()
        return np.asarray(self._embedder._model.encode(
            texts, batch_size=256, normalize_embeddings=True,
            show_progress_bar=verbose))

    # -- training --------------------------------------------------------
    def fit(self, texts: List[str], labels: Dict[str, np.ndarray],
            verbose: bool = True) -> Dict:
        from sklearn.linear_model import LogisticRegression

        if verbose:
            print("  embedding {} training segments...".format(len(texts)))
        X = self._embed(texts, verbose=verbose)

        report = {}
        for aspect in self.aspects:
            y = np.asarray(labels[aspect]).astype(int)
            if y.sum() < 30:
                if verbose:
                    print("  {:<16} only {} positives -- skipped".format(aspect, y.sum()))
                continue
            # balanced: the lexicon marks a small minority positive for most
            # aspects, and without reweighting the model learns to say "no".
            clf = LogisticRegression(max_iter=1000, C=1.0,
                                     class_weight="balanced", n_jobs=-1)
            clf.fit(X, y)
            self.models[aspect] = clf
            self.thresholds[aspect] = DEFAULT_PROB_THRESHOLD
            report[aspect] = {"positives": int(y.sum()),
                              "train_accuracy": round(float(clf.score(X, y)), 3)}
            if verbose:
                print("  {:<16} {:>7} positives   train acc {:.3f}".format(
                    aspect, int(y.sum()), report[aspect]["train_accuracy"]))
        return report

    # -- inference -------------------------------------------------------
    def probabilities(self, texts: List[str], verbose: bool = False) -> pd.DataFrame:
        X = self._embed(texts, verbose=verbose)
        out = {}
        for aspect, clf in self.models.items():
            out[aspect] = clf.predict_proba(X)[:, 1]
        return pd.DataFrame(out)

    def tag(self, texts: List[str], thresholds: Optional[Dict[str, float]] = None,
            verbose: bool = False) -> List[List[str]]:
        probs = self.probabilities(texts, verbose=verbose)
        thr = thresholds or self.thresholds
        return [[a for a in probs.columns
                 if row[a] >= thr.get(a, DEFAULT_PROB_THRESHOLD)]
                for _, row in probs.iterrows()]

    # -- persistence -----------------------------------------------------
    def save(self, path=None):
        path = path or MODEL_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as fh:
            pickle.dump({"models": self.models, "thresholds": self.thresholds,
                         "aspects": self.aspects}, fh)

    @classmethod
    def load(cls, path=None):
        path = path or MODEL_PATH
        with open(path, "rb") as fh:
            blob = pickle.load(fh)
        obj = cls(blob["aspects"])
        obj.models = blob["models"]
        obj.thresholds = blob["thresholds"]
        return obj


def available() -> bool:
    return MODEL_PATH.exists()
