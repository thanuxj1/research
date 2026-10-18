"""The two deployed models, chosen by the model comparison (scripts 57-59, trained by 61).

  topic    rule lexicon OR (bge-small sentence embedding -> RBF SVM per topic >= threshold)
           models/final/topic_svm.joblib
  verdict  RoBERTa-base fine-tuned on (topic, sentence) pairs -> N / X / P
           models/final/verdict_roberta/

One module, two callers: the batch pipeline (scripts/62_apply_final_models.py, which
feeds aggregate.py) and api.py's /analyse. Keeping a single definition is what stops
the dashboard and the API disagreeing -- see tests/test_api_pipeline_parity.py.

If the model files are absent (a fresh clone: models/ is gitignored), `available()`
is False and both callers fall back to the previous chain (lexicon + RoBERTa zero-shot
+ correction rules), which still works and is still tested.
"""
import threading
from typing import Dict, List, Sequence, Tuple

import numpy as np

from . import config as C
from .aspects import tag_segment
from .model_data import pair_text

FINAL_DIR = C.ROOT / "models" / "final"
TOPIC_PATH = FINAL_DIR / "topic_svm.joblib"
VERDICT_DIR = FINAL_DIR / "verdict_roberta"
VERDICT_CSV = C.DATA_PROCESSED / "verdict_final.csv"      # (segment_id, aspect, pol_fm)
MODEL_NAMES = {"topic": "embeddings (bge-small) + RBF SVM OR rule lexicon",
               "verdict": "RoBERTa-base fine-tuned on topic-sentence pairs"}

_lock = threading.Lock()
_topic = None
_embedder = None
_verdict = None


def available() -> bool:
    return TOPIC_PATH.exists() and (VERDICT_DIR / "config.json").exists()


def _load_topic():
    global _topic, _embedder
    with _lock:
        if _topic is None:
            import joblib
            from sentence_transformers import SentenceTransformer
            _topic = joblib.load(TOPIC_PATH)
            _embedder = SentenceTransformer(_topic["embedder"])
    return _topic, _embedder


def _load_verdict():
    global _verdict
    with _lock:
        if _verdict is None:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            tok = AutoTokenizer.from_pretrained(str(VERDICT_DIR))
            model = AutoModelForSequenceClassification.from_pretrained(str(VERDICT_DIR))
            model.eval()
            _verdict = (tok, model, torch, {int(k): v for k, v in model.config.id2label.items()})
    return _verdict


def embed(texts: Sequence[str], batch_size: int = 128) -> np.ndarray:
    _, emb = _load_topic()
    return emb.encode(list(texts), batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False)


def topics_from_embeddings(texts: Sequence[str], E: np.ndarray) -> np.ndarray:
    """Boolean matrix (len(texts), 7): lexicon OR svm >= threshold, in model_data.TOPICS order."""
    t, _ = _load_topic()
    lex = np.array([[k in set(tag_segment(s)) for k in t["topics"]] for s in texts], dtype=bool)
    if len(texts) == 0:
        return lex
    svm = np.column_stack([m.decision_function(E) >= th for m, th in zip(t["svms"], t["thresholds"])])
    return lex | svm


def tag_topics(texts: Sequence[str]) -> List[List[str]]:
    t, _ = _load_topic()
    P = topics_from_embeddings(texts, embed(texts))
    return [[k for k, on in zip(t["topics"], row) if on] for row in P]


def predict_verdicts(pairs: Sequence[Tuple[str, str]], batch_size: int = 64,
                     verbose: bool = False) -> List[Tuple[str, float]]:
    """pairs: (segment, topic) -> [(label N/X/P, confidence)], same order."""
    tok, model, torch, id2label = _load_verdict()
    out = []
    texts = [pair_text(topic, seg) for seg, topic in pairs]
    for i in range(0, len(texts), batch_size):
        enc = tok(texts[i:i + batch_size], truncation=True, max_length=96, padding=True, return_tensors="pt")
        with torch.no_grad():
            p = torch.softmax(model(**enc).logits, -1).numpy()
        out.extend((id2label[int(j)], float(row[j])) for row, j in zip(p, p.argmax(1)))
        if verbose and (i // batch_size) % 100 == 0:
            print("    verdicts %d / %d" % (min(i + batch_size, len(texts)), len(texts)), flush=True)
    return out


def analyse_piece(piece: str) -> Tuple[List[str], Dict[str, str]]:
    """What the deployed models say about one opinion unit: (topics, verdict per topic)."""
    topics = tag_topics([piece])[0]
    verdicts = predict_verdicts([(piece, k) for k in topics]) if topics else []
    return topics, {k: v[0] for k, v in zip(topics, verdicts)}
