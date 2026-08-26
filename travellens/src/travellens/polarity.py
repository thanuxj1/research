"""
LostinSriLanka -- Stage 5: polarity (complaint vs praise).

Stage 3 answered "what is this piece ABOUT". This stage answers
"is the visitor HAPPY or UNHAPPY about it".

Two methods are implemented so the thesis can compare them:

  METHOD A -- lexicon + negation (the baseline)
      Counts sentiment words, but flips polarity inside a negation window so
      that "not good" is not scored as positive. Transparent, instant, no
      model download. Its errors are the argument for Method B.

  METHOD B -- pretrained transformer (the system)
      distilbert-base-uncased-finetuned-sst-2-english reads word order and
      context. Trained on film reviews, NOT on tourism text -- a limitation we
      state openly and measure in Stage 6.

Both produce the same three labels so they can be scored against the same gold
set: N (negative), P (positive), X (neutral / no clear opinion).

Run with:  python scripts/06_polarity.py
"""
import re
from typing import Dict, List, Optional, Tuple

import pandas as pd

from . import config as C

# --------------------------------------------------------------------------
# METHOD A -- lexicon with negation handling
# --------------------------------------------------------------------------

POSITIVE_WORDS = {
    "good", "great", "nice", "beautiful", "excellent", "amazing", "awesome",
    "lovely", "wonderful", "clean", "peaceful", "calm", "friendly", "helpful",
    "worth", "best", "perfect", "stunning", "breathtaking", "gorgeous",
    "recommend", "recommended", "enjoyed", "enjoy", "comfortable", "easy",
    "well", "fine", "safe", "cheap", "affordable", "quiet", "fantastic",
    "superb", "pleasant", "impressive", "maintained", "organised", "organized",
}

NEGATIVE_WORDS = {
    "bad", "poor", "worst", "terrible", "awful", "dirty", "filthy", "rubbish",
    "garbage", "litter", "polluted", "smelly", "dangerous", "unsafe", "risky",
    "slippery", "crowded", "noisy", "expensive", "overpriced", "overcharge",
    "scam", "cheat", "difficult", "hard", "disappointing", "disappointed",
    "broken", "damaged", "neglected", "lacking", "missing", "waste",
    "unfortunately", "avoid", "horrible", "useless", "unfair", "rude",
    "harassment", "crowd", "mess", "messy", "worse", "problem", "issue",
}

# Words that flip the polarity of what follows them.
NEGATORS = {"not", "no", "never", "none", "cannot", "cant", "can't", "dont",
            "don't", "doesnt", "doesn't", "didnt", "didn't", "wasnt", "wasn't",
            "isnt", "isn't", "without", "hardly", "barely", "nothing", "nor"}

# How many words after a negator stay flipped. Three is the usual choice in the
# sentiment literature; it covers "not very good" without reaching into the
# next clause.
NEGATION_WINDOW = 3

# Requests for improvement. "need to clean" is a complaint even though "clean"
# is a positive word -- these phrases force a negative reading.
REQUEST_PATTERNS = re.compile(
    r"\b(need(s|ed)? to|should (be|have)|must be|have to be|ought to|"
    r"could be better|would be better|please (keep|clean|maintain|repair)|"
    r"hope they|wish they|if only|lack of|no proper|not enough)\b",
    re.IGNORECASE,
)

_TOKEN_RE = re.compile(r"[a-z']+")


def lexicon_polarity(text: str) -> Tuple[str, float]:
    """Method A. Returns (label, score) where score>0 is positive."""
    if not isinstance(text, str) or not text.strip():
        return "X", 0.0

    tokens = _TOKEN_RE.findall(text.lower())
    score = 0.0
    flip_until = -1

    for i, tok in enumerate(tokens):
        if tok in NEGATORS:
            flip_until = i + NEGATION_WINDOW
            continue
        value = 0.0
        if tok in POSITIVE_WORDS:
            value = 1.0
        elif tok in NEGATIVE_WORDS:
            value = -1.0
        if value and i <= flip_until:
            value = -value          # the negation flip
        score += value

    # A polite request to fix something is a complaint. Weight 2.0 so it
    # overcomes one positive word ("need to CLEAN the pond" = complaint).
    if REQUEST_PATTERNS.search(text):
        score -= 2.0

    if score > 0.5:
        return "P", score
    if score < -0.5:
        return "N", score
    return "X", score


# --------------------------------------------------------------------------
# METHOD B -- pretrained transformer
# --------------------------------------------------------------------------

MODEL_NAME = "distilbert-base-uncased-finetuned-sst-2-english"

# Method D's model. Trained on tweets: short, informal, frequently ungrammatical
# text written by non-native speakers -- structurally much closer to a Google
# Maps review than a film critic's paragraph is.
#
# The decisive property is not the training corpus but the LABEL SET. This model
# emits three classes (negative / neutral / positive), which is exactly the
# scheme our gold set uses. Method B had to fake a neutral class with a
# confidence threshold, and that failed: the model was over-confident (median
# 0.9994) so only 987 of 27,000 segments were ever called neutral, and factual
# statements such as "Entrance fee for one local is 150 LKR" were forced into
# complaint or praise.
ROBERTA_MODEL = "cardiffnlp/twitter-roberta-base-sentiment-latest"
ROBERTA_LABELS = {"negative": "N", "neutral": "X", "positive": "P",
                  "label_0": "N", "label_1": "X", "label_2": "P"}

# The model is binary: it always answers POSITIVE or NEGATIVE, never neutral.
# Our gold set has a neutral class (X) for factual statements. We recover it by
# treating low-confidence predictions as neutral. The threshold is a declared
# hyper-parameter, tuned once against the gold set -- not guessed per result.
NEUTRAL_BAND = 0.75


class TransformerPolarity:
    """Lazy-loaded so importing this module never triggers a download.

    Handles both the 2-class SST-2 model (Method B, neutral recovered from low
    confidence) and the 3-class Twitter model (Method D, native neutral).
    """

    def __init__(self, model_name: str = MODEL_NAME, batch_size: int = 64,
                 label_map=None):
        self.model_name = model_name
        self.batch_size = batch_size
        self.label_map = label_map          # None => 2-class threshold behaviour
        self._pipe = None

    def _load(self):
        if self._pipe is None:
            from transformers import pipeline
            self._pipe = pipeline(
                "sentiment-analysis",
                model=self.model_name,
                truncation=True,
                max_length=128,
                device=-1,          # CPU
            )
        return self._pipe

    def predict(self, texts: List[str], verbose: bool = True) -> List[Dict]:
        pipe = self._load()
        out = []
        total = len(texts)
        for start in range(0, total, self.batch_size):
            chunk = [t if isinstance(t, str) and t.strip() else "n/a"
                     for t in texts[start:start + self.batch_size]]
            for res in pipe(chunk):
                raw = res["label"]
                conf = float(res["score"])
                if self.label_map is not None:
                    # 3-class model: the neutral class is native, so no
                    # confidence threshold is needed or wanted.
                    label = self.label_map.get(raw.lower(), "X")
                else:
                    # 2-class model: neutral has to be synthesised from low
                    # confidence. See NEUTRAL_BAND for why this works poorly.
                    label = "X" if conf < NEUTRAL_BAND else (
                        "P" if raw.upper().startswith("POS") else "N")
                out.append({"label": label, "raw_label": raw, "confidence": round(conf, 4)})
            if verbose and (start // self.batch_size) % 20 == 0:
                print("    scored {}/{}".format(min(start + self.batch_size, total), total),
                      flush=True)
        return out


# --------------------------------------------------------------------------
# Corpus-level driver
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# METHOD C -- domain-corrected hybrid
#
# Why this exists
# ---------------
# distilbert-sst2 learned English from FILM reviews, where "quiet", "calm" and
# "slow" mean boring. In tourism they mean peaceful, which is praise. Measured
# on the deployed model:
#
#     "the place was calm"  -> NEGATIVE 0.936      "the movie was calm" -> NEGATIVE 0.989
#     "a slow walk"         -> NEGATIVE 0.993      "a slow movie"       -> NEGATIVE 1.000
#     "uncrowded"           -> NEGATIVE 0.996      "not touristy"       -> NEGATIVE 0.982
#
# The pairing is the evidence: the model gives a walk and a film the same
# reading, because it only ever learned the film one. 458 segments in this
# corpus are affected.
#
# This layer corrects that inversion CONSERVATIVELY, and is applied as a
# separate column (pol_hybrid) so the raw model output stays inspectable and
# the three methods can be compared against the gold set. It is a documented
# interim measure; the durable fix is fine-tuning on the annotated gold set,
# which this finding is the argument for.
# --------------------------------------------------------------------------

# Terms whose sentiment inverts between the general domain and tourism.
TOURISM_POSITIVE = re.compile(
    r"\b(calm|quiet|peaceful|serene|tranquil|silent|uncrowded|un ?spoil(ed|t)|"
    r"less crowded|not crowded|not touristy|off the beaten|secluded|"
    r"untouched|undisturbed|relaxing|soothing|slow paced)\b",
    re.IGNORECASE,
)


def hybrid_polarity(text, model_label, lexicon_label, lexicon_score):
    """Method C. Returns (label, was_overridden).

    The override fires only when every one of these holds:
      * the model said NEGATIVE
      * a domain-inverted term is present
      * the lexicon independently said POSITIVE
      * no negative word and no improvement request appear in the text

    All four together make a false positive unlikely: the text must look like
    praise by an independent method AND contain no complaint evidence at all.
    """
    if model_label != "N":
        return model_label, False
    if not TOURISM_POSITIVE.search(text or ""):
        return model_label, False
    if lexicon_label != "P" or lexicon_score < 1.0:
        return model_label, False
    tokens = set(_TOKEN_RE.findall((text or "").lower()))
    if tokens & NEGATIVE_WORDS:
        return model_label, False
    if REQUEST_PATTERNS.search(text or ""):
        return model_label, False
    return "P", True


# --------------------------------------------------------------------------
# METHOD E -- the deployed classifier: Method D plus one correction
#
# Method D reads sentiment correctly for the tourism domain, but it treats a
# politely-phrased complaint as a statement of fact:
#
#     "but need to clean the pond area and the surroundings."  -> neutral 0.742
#
# The visitor is complaining. They are just being courteous about it, and the
# model has no way to know that "need to" carries a grievance in review text.
# Both Method A and Method B get this right, so the signal is available -- it
# simply is not in D.
#
# The correction is narrow: a request phrase, and an independent negative
# reading from the lexicon, and D not already saying negative. Requiring the
# lexicon to agree keeps this from firing on neutral uses of "should" such as
# "you should visit early".
# --------------------------------------------------------------------------
# Explicit physical-hazard vocabulary. Narrower than the safety ASPECT triggers
# in config: those include neutral topic words like "monkeys" and "deep", which
# appear in plain descriptions. These are words that only appear when a hazard
# is being asserted.
HAZARD_WORDS = re.compile(
    r"\b(dangerous|danger|unsafe|risky|risk|slipper(y|ing)|drown(ed|ing)?|"
    r"hazard(ous)?|accident|fatal|died|death|deadly|treacherous)\b",
    re.IGNORECASE,
)

# Hedges. A hedged warning is still a warning.
HEDGE_WORDS = re.compile(
    r"\b(maybe|may be|might|possibly|perhaps|somewhat|a bit|slightly|"
    r"can be|could be|sometimes|if it rains|during the monsoon)\b",
    re.IGNORECASE,
)


def safety_recall_rule(text, label, aspect_is_safety, lexicon_label):
    """Recover hedged safety warnings that the model rounds down to neutral.

    Measured problem: "maybe a bit dangerous for small children" and "might be
    slippery when it rains" are both classified NEUTRAL at low confidence. Both
    are warnings, and dropping them removes exactly the signal this project
    exists to surface.

    The asymmetry is deliberate and is the justification for the rule: showing a
    mild warning that turns out to be minor costs a reader very little; hiding a
    real one can cost a great deal. For safety alone, recall is preferred to
    precision. No other aspect gets this treatment.

    Fires only when: the segment is tagged safety, the model said neutral, an
    explicit hazard word is present, and the lexicon does not read it as
    positive -- so "not dangerous at all" and "perfectly safe" are unaffected,
    because the lexicon's negation handling scores those positive.
    """
    if not aspect_is_safety or label != "X":
        return label, False
    if not HAZARD_WORDS.search(text or ""):
        return label, False
    if lexicon_label == "P":
        return label, False
    return "N", True


def final_polarity(text, roberta_label, lexicon_label, lexicon_score):
    """Method E. Returns (label, was_corrected).

    The safety recall rule is applied separately in the aspect-aware path,
    since it depends on which aspect the segment is being scored for.
    """
    if roberta_label == "N":
        return "N", False
    if not REQUEST_PATTERNS.search(text or ""):
        return roberta_label, False
    if lexicon_label != "N":
        return roberta_label, False
    return "N", True


# Each model keeps its own cache: the same text gets different answers from
# different models, so one shared cache would silently mix them.
def _cache_path(model_name: str):
    slug = model_name.split("/")[-1].replace("-", "_")
    return C.DATA_PROCESSED / "polarity_cache_{}.csv".format(slug)


# --------------------------------------------------------------------------
# METHOD F -- the model trained on this project's own data.
#
# Produced by scripts/11_finetune.py. Differs from every method above in one
# structural way: it takes the ASPECT as part of its input, so a single
# sentence can receive different verdicts for different aspects:
#
#     "Roads & Access: the road was rough but the view was worth it"   -> N
#     "Scenery & Nature: the road was rough but the view was worth it" -> P
#
# Methods A-E cannot do this -- they give one verdict per segment and every
# aspect on that segment inherits it. This is what "aspect-based" sentiment
# actually requires, and it is the main reason to train rather than borrow.
#
# Falls back silently if the model has not been trained yet; the pipeline runs
# on Method E in that case.
# --------------------------------------------------------------------------
TRAINED_MODEL_DIR = C.ROOT / "models" / "travellens-polarity"
TRAINED_CACHE = C.DATA_PROCESSED / "polarity_cache_trained.csv"


def trained_model_available() -> bool:
    return (TRAINED_MODEL_DIR / "config.json").exists()


class TrainedPolarity:
    """Aspect-aware classifier loaded from the locally trained checkpoint."""

    def __init__(self, model_dir=None, batch_size: int = 32):
        self.model_dir = str(model_dir or TRAINED_MODEL_DIR)
        self.batch_size = batch_size
        self._model = None
        self._tok = None
        self._id2label = None

    def _load(self):
        if self._model is None:
            import torch
            from transformers import (AutoModelForSequenceClassification,
                                      AutoTokenizer)
            self._tok = AutoTokenizer.from_pretrained(self.model_dir)
            self._model = AutoModelForSequenceClassification.from_pretrained(
                self.model_dir)
            self._model.eval()
            cfg = self._model.config
            self._id2label = {int(k): v for k, v in cfg.id2label.items()}
            self._torch = torch
        return self._model

    @staticmethod
    def format_input(text: str, aspect_key: str) -> str:
        """Must match finetune.format_input exactly, or the model sees a
        different input shape at inference than it was trained on."""
        return "{}: {}".format(C.ASPECTS[aspect_key].label, text)

    def predict_pairs(self, pairs: List, verbose: bool = True) -> List[str]:
        """pairs: list of (text, aspect_key). Returns labels in the same order."""
        self._load()
        torch = self._torch
        out = []
        total = len(pairs)
        for start in range(0, total, self.batch_size):
            chunk = pairs[start:start + self.batch_size]
            texts = [self.format_input(t, a) for t, a in chunk]
            enc = self._tok(texts, truncation=True, max_length=128,
                            padding=True, return_tensors="pt")
            with torch.no_grad():
                logits = self._model(**enc).logits
            for idx in logits.argmax(dim=1).tolist():
                out.append(self._id2label[idx])
            if verbose and (start // self.batch_size) % 50 == 0:
                print("    scored {}/{}".format(min(start + self.batch_size, total),
                                                total), flush=True)
        return out


def score_aspects_trained(seg: pd.DataFrame, use_cache: bool = True,
                          verbose: bool = True) -> pd.DataFrame:
    """Long table: one row per (segment, aspect) with the trained verdict."""
    rows = []
    for key in C.ASPECTS:
        sub = seg[seg["asp_" + key] & (seg["n_aspects"] > 0)]
        for sid, text in zip(sub["segment_id"], sub["segment"]):
            rows.append({"segment_id": sid, "aspect": key, "text": str(text)})
    long = pd.DataFrame(rows)
    if long.empty:
        return long

    cache = {}
    if use_cache and TRAINED_CACHE.exists():
        cdf = pd.read_csv(TRAINED_CACHE)
        cache = {(r.text, r.aspect): r.label for r in cdf.itertuples(index=False)}

    todo = sorted({(t, a) for t, a in zip(long["text"], long["aspect"])
                   if (t, a) not in cache})
    if verbose:
        print("    cache hit : {} / {} pairs".format(len(long) - len(todo), len(long)))
        print("    to score  : {} new (text, aspect) pairs".format(len(todo)))

    if todo:
        labels = TrainedPolarity().predict_pairs(todo, verbose=verbose)
        for (t, a), lab in zip(todo, labels):
            cache[(t, a)] = lab
        if use_cache:
            pd.DataFrame([{"text": t, "aspect": a, "label": l}
                          for (t, a), l in cache.items()]).to_csv(
                TRAINED_CACHE, index=False, encoding="utf-8")

    long["pol_trained"] = [cache[(t, a)] for t, a in zip(long["text"], long["aspect"])]
    return long[["segment_id", "aspect", "pol_trained"]]


CACHE_PATH = C.DATA_PROCESSED / "polarity_cache.csv"


def _load_cache(path=None) -> Dict[str, Dict]:
    """Previously scored segment text -> prediction.

    Keyed by the text itself, not by segment_id: identical wording at two
    destinations is the same classification problem, and reviewers repeat
    phrases constantly ("the road is very bad").
    """
    path = path or CACHE_PATH
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    return {r.text: {"label": r.label, "confidence": r.confidence}
            for r in df.itertuples(index=False)}


def _save_cache(cache: Dict[str, Dict], path=None) -> None:
    path = path or CACHE_PATH
    C.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"text": k, "label": v["label"], "confidence": v["confidence"]}
                  for k, v in cache.items()]).to_csv(
        path, index=False, encoding="utf-8")


def _score_with_model(texts, model_name, label_map, cache_path,
                      use_cache=True, verbose=True):
    """Score `texts` with one model, consulting and updating its own cache."""
    cache = _load_cache(cache_path) if use_cache else {}
    todo = sorted(set(t for t in texts if t not in cache))
    if verbose:
        print("    cache hit : {} / {}".format(len(texts) - sum(
            1 for t in texts if t not in cache), len(texts)))
        print("    to score  : {} new unique texts".format(len(todo)))
    if todo:
        preds = TransformerPolarity(model_name, label_map=label_map).predict(
            todo, verbose=verbose)
        for text, pred in zip(todo, preds):
            cache[text] = {"label": pred["label"], "confidence": pred["confidence"]}
        if use_cache:
            _save_cache(cache, cache_path)
    return ([cache[t]["label"] for t in texts],
            [cache[t]["confidence"] for t in texts])


def score_corpus(seg: pd.DataFrame, use_transformer: bool = True,
                 only_tagged: bool = True, use_cache: bool = True,
                 verbose: bool = True) -> pd.DataFrame:
    """Add polarity columns for both methods to the tagged segment table.

    With use_cache=True only text never scored before is sent to the model, so
    a refresh that adds 200 reviews costs seconds rather than re-scoring the
    whole corpus.
    """
    seg = seg.copy()
    target = seg["n_aspects"] > 0 if only_tagged else ~seg["too_short"]

    if verbose:
        print("  scoring {} segments".format(int(target.sum())))

    # -- Method A: cheap, always recomputed ---------------------------------
    lex = seg.loc[target, "segment"].map(lexicon_polarity)
    seg.loc[target, "pol_lexicon"] = lex.map(lambda t: t[0])
    seg.loc[target, "pol_lexicon_score"] = lex.map(lambda t: t[1])
    if verbose:
        print("  method A (lexicon) done")

    if not use_transformer:
        return seg

    texts = seg.loc[target, "segment"].astype(str).tolist()
    lex_labels = seg.loc[target, "pol_lexicon"].tolist()
    lex_scores = seg.loc[target, "pol_lexicon_score"].tolist()

    # Create the output columns up front with object dtype. Assigning booleans
    # into a column pandas has inferred as float raises a FutureWarning now and
    # will be an error in a later pandas.
    for col in ("pol_model", "pol_hybrid", "pol_roberta", "pol_final",
                "pol_overridden", "pol_final_corrected"):
        if col not in seg.columns:
            seg[col] = pd.Series([pd.NA] * len(seg), dtype="object")

    # -- Method B: SST-2, film domain, 2 classes ----------------------------
    if verbose:
        print("  method B (SST-2, film domain)")
    b_lab, b_conf = _score_with_model(
        texts, MODEL_NAME, None, CACHE_PATH, use_cache, verbose)
    seg.loc[target, "pol_model"] = b_lab
    seg.loc[target, "pol_model_conf"] = b_conf

    # -- Method C: B plus the hand-written domain patch ---------------------
    c = [hybrid_polarity(t, m, ll, ls)
         for t, m, ll, ls in zip(texts, b_lab, lex_labels, lex_scores)]
    seg.loc[target, "pol_hybrid"] = [r[0] for r in c]
    seg.loc[target, "pol_overridden"] = [r[1] for r in c]
    if verbose:
        print("  method C (B + domain patch): {} labels corrected N->P".format(
            sum(1 for r in c if r[1])))

    # -- Method D: Twitter-RoBERTa, 3 native classes ------------------------
    if verbose:
        print("  method D (Twitter-RoBERTa, 3-class)")
    d_lab, d_conf = _score_with_model(
        texts, ROBERTA_MODEL, ROBERTA_LABELS, _cache_path(ROBERTA_MODEL),
        use_cache, verbose)
    seg.loc[target, "pol_roberta"] = d_lab
    seg.loc[target, "pol_roberta_conf"] = d_conf

    # -- Method E: D plus the polite-request correction (deployed) ----------
    e = [final_polarity(t, d, ll, ls)
         for t, d, ll, ls in zip(texts, d_lab, lex_labels, lex_scores)]
    seg.loc[target, "pol_final"] = [r[0] for r in e]
    seg.loc[target, "pol_final_corrected"] = [r[1] for r in e]
    if verbose:
        print("  method E (D + request rule): {} labels corrected -> N".format(
            sum(1 for r in e if r[1])))

    return seg


def main():
    print("\nLostinSriLanka -- Stage 5: polarity\n" + "=" * 60)
    seg = pd.read_csv(C.DATA_PROCESSED / "segments_tagged.csv")
    seg = score_corpus(seg, use_transformer=True, only_tagged=True)

    out = C.DATA_PROCESSED / "segments_scored.csv"
    seg.to_csv(out, index=False, encoding="utf-8")

    scored = seg[seg["n_aspects"] > 0]
    print("\n  agreement between the two methods:")
    both = scored.dropna(subset=["pol_lexicon", "pol_model"])
    agree = float((both["pol_lexicon"] == both["pol_model"]).mean())
    print("    they agree on {:.1f}% of segments".format(100 * agree))
    print("    (where they disagree, one of them is wrong -- Stage 6 says which)")

    print("\n  label distribution")
    print("  {:<12} {:>8} {:>8}".format("", "lexicon", "model"))
    for lab in ["N", "P", "X"]:
        print("  {:<12} {:>8} {:>8}".format(
            lab, int((scored["pol_lexicon"] == lab).sum()),
            int((scored["pol_model"] == lab).sum())))
    print("\nwrote {}".format(out))


if __name__ == "__main__":
    main()


# --------------------------------------------------------------------------
# Site rules are not complaints
#
# Open problem #3 in the README: "site rules ('no polythene allowed') counted
# as cleanliness complaints". Measured before fixing -- 18 segments, all of
# this shape:
#
#     "Its is prohibited to take polythene, plastic bottles inside the park."
#     "Not allowed to bring any plastic or polythene."
#
# The visitor is reporting a regulation, and often approvingly: several of
# these sit next to "that's the main reason the place is kept clean". The
# model reads the prohibition words as negative sentiment about litter.
#
# Note what this is: a THIRD hand-written rule, added to a pipeline whose
# dependence on the other two was just quantified at up to 6.9 pp. It is
# therefore narrow, off-switchable, and included in the ablation. It fires only
# when the segment states a prohibition AND carries no word describing a bad
# experience -- so "not allowed to swim, the current is dangerous" and
# "prohibited but people litter anyway" are untouched.
# --------------------------------------------------------------------------
PROHIBITION = re.compile(
    r"\b(not allowed|isn'?t allowed|aren'?t allowed|no longer allowed|"
    r"prohibit(ed|s)?|forbidden|banned|not permitted|restricted from|"
    r"must not (take|bring|carry)|cannot (take|bring|carry))\b", re.IGNORECASE)

# Words that mean the visitor is describing a bad experience rather than
# reporting a regulation. Any of these and the rule stands down.
_COMPLAINT_EVIDENCE = re.compile(
    r"\b(dirty|filthy|litter(ed|ing)?|rubbish|garbage|waste[sd]?|smell(y|s)?|"
    r"stink(s|ing)?|mess(y)?|unclean|disgusting|everywhere|neglected|"
    r"poor|bad|awful|terrible|horrible|worst|shame|sad|unfortunately)\b",
    re.IGNORECASE)


def site_rule_is_not_a_complaint(text, label):
    """(label, fired). Turns a reported regulation from N into X.

    X, not P: the visitor has not praised anything, they have described a
    rule. Counting it as praise would be the mirror of the error being fixed.
    """
    if label != "N":
        return label, False
    body = text or ""
    if not PROHIBITION.search(body):
        return label, False
    if _COMPLAINT_EVIDENCE.search(body):
        return label, False
    # A prohibition that comes WITH a hazard is a warning, not a regulation:
    # "not allowed to swim here, the current is dangerous". Neutralising that
    # would erase the exact class of warning the safety recall rule exists to
    # recover -- one rule must not undo another.
    if HAZARD_WORDS.search(body):
        return label, False
    return "X", True
