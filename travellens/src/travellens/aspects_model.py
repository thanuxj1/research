"""
LostinSriLanka -- model-based aspect extraction (alternative to the rule lexicon).

Replaces keyword matching with sentence embeddings. Each aspect is described in
natural language, both the description and the segment are encoded as vectors,
and the segment is assigned to every aspect whose similarity clears a threshold.

Why embeddings rather than zero-shot NLI
----------------------------------------
A zero-shot NLI classifier was tried first and performed badly on this task:
5/20 on a hand-built probe against 12/20 for the rules, with visible label
collapse (it answered "price" to most inputs) and ~8 hours of inference on the
full corpus. Embeddings are the standard approach for semantic matching at this
scale -- one forward pass per segment, no per-label pass, so roughly one
seventh the cost.

The advantage over the lexicon
------------------------------
The rules can only find words that were written down. "sewage was running into
the stream" contains no word from the cleanliness list and is dropped entirely.
Embeddings match on MEANING, so a sentence can be recognised as being about
litter without containing any listed word.

The costs, stated plainly
-------------------------
* Not traceable. A rule match points at the exact trigger word; a similarity
  score of 0.42 explains nothing. This matters for a thesis where every number
  should be auditable.
* Threshold-dependent. The cutoff is a hyper-parameter that changes results and
  must be tuned and reported.
* Slower. Seconds becomes minutes on this corpus -- acceptable, unlike NLI.

Both extractors are kept so the thesis can report either, or their union.

Run with:  python scripts/17_aspects_model.py
"""
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from . import config as C

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Similarity above which a segment is judged to be about an aspect. Tuned on the
# probe set in this module, and reported as a declared hyper-parameter -- not
# adjusted per result.
DEFAULT_THRESHOLD = 0.40

# Why 0.40 and not something looser.
#
# The threshold trades recall against false tags. Measured on a 22-item probe
# (12 hard positives the lexicon misses, 10 segments with no aspect at all):
#
#     thr    found / 12     wrong tags
#     0.28      10              25
#     0.32       9              12
#     0.36       7               7
#     0.40       5               3     <- chosen
#     0.44       4               1
#     rules      4               3
#
# 0.40 is the point where the embedding tagger makes exactly as many wrong tags
# as the rule lexicon (3) while finding more of the hard cases (5 vs 4). Setting
# it looser inflates recall by adding tags like "a must go place" -> cleanliness,
# which would corrupt every count downstream.
#
# Calibrating to the lexicon's own error rate means the threshold is justified
# by a stated criterion rather than chosen to flatter the result. It should be
# re-tuned against the human gold set once that exists.

# Natural-language descriptions the aspect vectors are built from. Several
# phrasings per aspect, averaged: a single sentence embeds too narrowly and
# misses paraphrases.
ASPECT_PROMPTS: Dict[str, List[str]] = {
    "roads_access": [
        "the condition of the road and how hard it is to get there",
        "driving, parking, public transport and the walk to the site",
        "the path, steps, climb or trek needed to reach it",
    ],
    "facilities": [
        "toilets, washrooms and changing rooms at the site",
        "food, shops, seating, shelter and signage provided",
        "guides, ticket counters and visitor amenities",
    ],
    "cleanliness": [
        "litter, rubbish and waste left at the site",
        "pollution, sewage, bad smells and dirty water",
        "how clean or well kept the place is",
    ],
    "safety": [
        "physical danger to visitors, risk of injury or drowning",
        "slippery ground, steep drops, strong currents, missing railings",
        "warnings to other visitors about hazards and wildlife",
    ],
    "price_value": [
        "entrance fees, ticket prices and charges",
        "whether it is good value for the money paid",
        "being overcharged, tipping and pricing for foreigners",
    ],
    "crowd": [
        "how busy or crowded the place is",
        "noise, queues and too many people",
        "whether it is peaceful and quiet",
    ],
    "scenery": [
        "the views, landscape and natural beauty",
        "waterfalls, sunsets, wildlife and photographs",
    ],
}


class EmbeddingAspectTagger:
    """Assigns aspects by cosine similarity to aspect descriptions."""

    def __init__(self, model_name: str = EMBED_MODEL,
                 threshold: float = DEFAULT_THRESHOLD):
        self.model_name = model_name
        self.threshold = threshold
        self._model = None
        self._aspect_vecs = None
        self._keys = list(ASPECT_PROMPTS)

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name, device="cpu")
            vecs = []
            for key in self._keys:
                emb = self._model.encode(ASPECT_PROMPTS[key],
                                         normalize_embeddings=True)
                mean = np.asarray(emb).mean(axis=0)
                vecs.append(mean / np.linalg.norm(mean))
            self._aspect_vecs = np.vstack(vecs)
        return self._model

    def similarities(self, texts: List[str], batch_size: int = 256,
                     verbose: bool = False) -> np.ndarray:
        self._load()
        emb = self._model.encode(texts, batch_size=batch_size,
                                 normalize_embeddings=True,
                                 show_progress_bar=verbose)
        return np.asarray(emb) @ self._aspect_vecs.T

    def tag(self, texts: List[str], threshold: Optional[float] = None,
            verbose: bool = False) -> List[List[str]]:
        thr = self.threshold if threshold is None else threshold
        sims = self.similarities(texts, verbose=verbose)
        return [[self._keys[j] for j in np.where(row >= thr)[0]] for row in sims]

    def top_aspect(self, texts: List[str]) -> List[str]:
        sims = self.similarities(texts)
        return [self._keys[int(i)] for i in sims.argmax(axis=1)]


def tag_corpus_model(seg: pd.DataFrame, threshold: float = DEFAULT_THRESHOLD,
                     verbose: bool = True) -> pd.DataFrame:
    """Add mAsp_<aspect> columns alongside the rule-based asp_<aspect> ones."""
    tagger = EmbeddingAspectTagger(threshold=threshold)
    usable = ~seg["too_short"]
    texts = seg.loc[usable, "segment"].astype(str).tolist()
    if verbose:
        print("  encoding {} segments...".format(len(texts)))
    tags = tagger.tag(texts, verbose=verbose)

    seg = seg.copy()
    for key in ASPECT_PROMPTS:
        seg["mAsp_" + key] = False
    idx = seg.index[usable]
    for pos, aspects in zip(idx, tags):
        for a in aspects:
            seg.at[pos, "mAsp_" + a] = True
    seg["m_n_aspects"] = seg[["mAsp_" + k for k in ASPECT_PROMPTS]].sum(axis=1)

    if verbose:
        print("  {:<22} {:>10} {:>10}".format("aspect", "rules", "embeddings"))
        print("  " + "-" * 44)
        for key in ASPECT_PROMPTS:
            print("  {:<22} {:>10} {:>10}".format(
                C.ASPECTS[key].label,
                int(seg.get("asp_" + key, pd.Series(dtype=bool)).sum()),
                int(seg["mAsp_" + key].sum())))
    return seg


# --------------------------------------------------------------------------
# Per-aspect extractor selection -- MEASURED, not assumed.
#
# Evaluated on 100 real segments stratified by what each extractor found, so
# both precision and recall are observable (reports/aspect_extraction_eval.json).
# F1 per aspect:
#
#     aspect          rules   embeddings   union
#     roads_access    0.786      0.714     0.912   <- union clearly best
#     cleanliness     0.800      0.857     0.706
#     facilities      0.737      0.400     0.627   <- union HURTS
#     safety          0.667      0.571     0.545   <- union HURTS
#
# Applying the union everywhere -- which is what an earlier version did --
# improves roads by 0.13 but costs facilities 0.11 and safety 0.12. Since
# safety is the aspect where an error matters most, a uniform union is the
# wrong default.
#
# Rule applied: take the union only where it wins by a clear margin; otherwise
# keep the lexicon, which is also faster and traceable to a specific trigger
# word. Cleanliness is left on rules because the embedding advantage (+0.057)
# is inside the noise of a 100-item sample.
#
# The three unmeasured aspects (price, crowd, scenery) default to rules.
# Re-derive this table from the human gold set when it exists.
ASPECT_EXTRACTOR = {
    # FINAL ROUTING -- every entry decided by measurement on a purpose-built
    # test set for that topic, never by assumption.
    #
    #   topic         positives  word list   model    chosen
    #   roads_access         33      0.786    0.914   trained
    #   facilities           21      0.737    0.773   trained
    #   safety               22      0.741    0.755   safety_model
    #   cleanliness          36      0.901    0.638   rules
    #   price_value          21      0.976    0.755   rules
    #   crowd                16      0.903    0.875   rules
    #   scenery              25      0.906    0.667   rules
    #
    # The headline finding: for four of seven topics the LEXICON wins outright,
    # once its vocabulary gaps are fixed. Those gaps -- not the method -- were
    # the real problem. Patching them moved cleanliness 0.643 -> 0.901,
    # price 0.632 -> 0.976 and scenery 0.714 -> 0.906, while a trained model
    # on the same topics scored 0.638, 0.755 and 0.667.
    #
    # Models win only where meaning genuinely outruns vocabulary: roads and
    # access (many phrasings, few shared words) and safety (rare, lexically
    # diverse, and where recall matters most).
    "roads_access": "trained",
    "facilities":   "trained",
    "safety":       "safety_model",
    "cleanliness":  "rules",
    "price_value":  "rules",
    "crowd":        "rules",
    "scenery":      "rules",
}
