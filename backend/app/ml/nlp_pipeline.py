"""
NLP Pipeline — Tourism Safety Scam Analytics Engine
IT22629180

Hybrid two-tier classifier:
  Tier 1 (fast): TF-IDF + RandomForest (.joblib)
  Tier 2 (deep): HuggingFace zero-shot classification (when available)
Sentiment: cardiffnlp/twitter-roberta-base-sentiment-latest (or TextBlob fallback)
"""

import os
import re
import joblib
from collections import Counter
from typing import Dict, Optional

# ─── Optional heavy imports (graceful degradation) ───────────────────────────
try:
    from transformers import pipeline as hf_pipeline
    _HF_AVAILABLE = True
except ImportError:
    _HF_AVAILABLE = False

try:
    from textblob import TextBlob
    _TEXTBLOB_AVAILABLE = True
except ImportError:
    _TEXTBLOB_AVAILABLE = False


# ─── Scam & Incident Taxonomy ───────────────────────────────────────────────────
SCAM_TAXONOMY: Dict[str, list] = {
    # Scams & Fraud
    "Gem Scam":          ["gem scam", "fake gem", "gem shop scam", "gem store scam", "overpriced gem", "ruby scam", "sapphire scam", "moonstone scam", "fake jewel", "fake stone"],
    "Commission Shop":   ["commission shop", "commission store", "driver commission", "shop commission", "took me to a shop", "took us to a shop", "spice garden scam", "forced to buy at shop"],
    "Tuk Tuk Scam":      ["tuk tuk scam", "tuk-tuk scam", "tuktuk scam", "three-wheeler scam", "tuk tuk overcharged", "tuk tuk driver lied", "tuk tuk refusal", "tuk tuk rip off"],
    "Overcharging":      ["overcharged", "ripped off", "double price", "tourist price", "too expensive", "charged extra", "inflated price", "10x the price", "extortion"],
    "Fake Guide":        ["fake guide", "unofficial guide", "unauthorized guide", "not licensed guide", "demanded money", "fake monk"],
    "Transport Fraud":   ["taxi scam", "refused meter", "tampered meter", "agreed price changed", "wrong route", "airport taxi scam", "bus scam", "train ticket tout"],
    "Accommodation Scam":["hotel scam", "different room", "bait switch", "fake booking", "different property", "dirty room", "no refund"],
    "Food/Menu Scam":    ["fake menu", "surprise bill", "tourist menu", "service charge scam", "overcharged food"],
    
    # Crime & Danger
    "Theft / Robbery":   ["theft", "stolen", "pickpocket", "mugged", "robbed", "bag snatched", "phone stolen", "passport stolen", "break in", "burglar"],
    "Physical Assault":  ["attack", "assault", "hit", "punched", "beaten", "violent", "threw", "physical altercation", "chased"],
    "Harassment":        ["harassed", "followed", "uncomfortable", "touched", "catcalling", "stalked", "wouldn't leave me alone", "creep", "groped", "sexual harassment", "beach boy"],
    
    # Hazards & Health
    "Accident / Hazard": ["accident", "crash", "injured", "hospital", "fell", "dangerous road", "reckless driving", "almost died"],
    "Health / Hygiene":  ["food poisoning", "sick", "vomiting", "diarrhea", "hospitalized", "dirty water", "unhygienic", "bed bugs", "rats", "cockroaches"],
    "Unsafe Area":       ["unsafe area", "dangerous area", "avoid at night", "sketchy area", "threatened", "intimidated", "gang", "mafia"],
}

# HARD_EXCLUSIONS to be used in filtering logic
HARD_EXCLUSIONS = [
    "foreign nationals arrested", "foreigners arrested",
    "racket busted", "arrested for online", "arrested for fraud",
    "nationals arrested", "chinese nationals", "indian nationals",
    "suspects arrested", "suspects detained",
    "cyber fraud ring", "call center scam", "investment scam ring",
    "online gambling", "money laundering", "financial crime",
    "police raid", "special raid", "cid arrested",
    "residing in", "on visa", "overstaying", "illegal stay",
    
    # Government, Diplomatic & News Exclusions
    "high commissioner", "high commission", "deputy high commissioner",
    "land reforms commission", "elections commissioner", "elections commission",
    "presidential commission", "bribery commission", "human rights commission",
    "police commission", "cabinet sub committee", "french embassy",
    "un high commissioner", "charity commission", "commission to investigate",
    "commissioner of", "lrc director", "election official", "polling booth",
    "ballot paper", "annulled as a group", "district secretary", "local council",
    "disaster management", "affected by floods", "heavy showers", "met dept",
    "meteorology", "sluice gates", "evacuation drills", "river levels",
    "dmc reported", "disaster management center", "disaster management centre",
    "port agreement", "haj pilgrimage",
    
    "thailand", "pattaya", "bangkok", "phuket", "bali", "indonesia",
    "europe", "italy", "rome", "paris", "france", "spain", "barcelona", "madrid",
    "london", "united kingdom", "british", "tenerife", "mallorca", "greece", "athens",
    "prague", "shanghai", "vietnam", "cambodia", "philippines",
    "dubai", "kuwait", "qatar", "saudi arabia", "oman", "middle east",
    "employment", "job racket", "domestic work", "work visa", "sending women",
]

# Sri Lanka location dictionary → (lat, lon)
SL_LOCATIONS: Dict[str, tuple] = {
    "colombo fort":    (6.9344, 79.8428),
    "colombo":         (6.9271, 79.8612),
    "kandy":           (7.2906, 80.6337),
    "galle fort":      (6.0535, 80.2210),
    "galle":           (6.0535, 80.2210),
    "ella":            (6.8728, 81.0464),
    "sigiriya":        (7.9573, 80.7600),
    "negombo":         (7.2083, 79.8358),
    "mirissa":         (5.9483, 80.4716),
    "arugam bay":      (6.8399, 81.8325),
    "nuwara eliya":    (6.9497, 80.7891),
    "trincomalee":     (8.5874, 81.2152),
    "hikkaduwa":       (6.1395, 80.1061),
    "mount lavinia":   (6.8297, 79.8661),
    "unawatuna":       (5.9997, 80.2489),
    "bentota":         (6.4221, 80.0009),
    "matara":          (5.9549, 80.5550),
    "jaffna":          (9.6615, 80.0255),
    "anuradhapura":    (8.3114, 80.4037),
    "polonnaruwa":     (7.9396, 81.0009),
    "dambulla":        (7.8675, 80.6517),
    "pinnawala":       (7.3014, 80.3844),
    "airport":         (7.1806, 79.8841),
    "bandaranaike":    (7.1806, 79.8841),
    "katunayake":      (7.1806, 79.8841),
    "fort":            (6.9344, 79.8428),
    "pettah":          (6.9358, 79.8535),
    "weligama":        (5.9748, 80.4282),
    "tangalle":        (6.0252, 80.7960),
    "tissamaharama":   (6.2833, 81.2833),
    "yala":            (6.3667, 81.5167),
    "haputale":        (6.7667, 80.9667),
    "badulla":         (6.9931, 81.0549),
    "hatton":          (6.8939, 80.5956),
    "nuwara":          (6.9497, 80.7891),
    "temple of tooth": (7.2936, 80.6413),
    "nine arch bridge":(6.8770, 81.0590),
}


# Tourism-relevance filter keywords
TOURISM_KEYWORDS = [
    "tourist", "tourism", "travel", "visit", "sri lanka", "lanka",
    "backpacker", "hotel", "hostel", "beach", "temple", "safari",
    "scam", "warning", "traveler", "traveller", "vacation", "holiday",
    "guesthouse", "tuk", "guide", "tour",
]


class NLPPipeline:
    """
    Main NLP analysis pipeline for the Safety Heatmap engine.
    Falls back gracefully when heavyweight models are unavailable.
    """

    def __init__(self):
        self._classifier = None      # TF-IDF + RF joblib model
        self._sentiment_pipe = None  # HuggingFace sentiment
        self._zero_shot = None       # HuggingFace zero-shot
        self._load_models()

    def _load_models(self):
        # Tier 1: Fast sklearn model
        model_path = os.path.join(
            os.path.dirname(__file__), "models", "scam_classifier.joblib"
        )
        if os.path.exists(model_path):
            self._classifier = joblib.load(model_path)
            print("[NLP] Loaded TF-IDF + RF classifier from disk.")
        else:
            print("[NLP] No trained classifier found — rule-based fallback active.")

        # Tier 2: HuggingFace (optional — heavy download on first run)
        if _HF_AVAILABLE:
            try:
                self._sentiment_pipe = hf_pipeline(
                    "sentiment-analysis",
                    model="cardiffnlp/twitter-roberta-base-sentiment-latest",
                    truncation=True,
                    max_length=512,
                )
                print("[NLP] Loaded HuggingFace sentiment model.")
            except Exception as e:
                print(f"[NLP] HuggingFace sentiment unavailable: {e}")
                
            try:
                self._zero_shot = hf_pipeline(
                    "zero-shot-classification",
                    model="typeform/distilbert-base-uncased-mnli",
                )
                print("[NLP] Loaded HuggingFace zero-shot classification model (DistilBERT-MNLI).")
            except Exception as e:
                print(f"[NLP] HuggingFace zero-shot unavailable: {e}")

    # ── Public API ──────────────────────────────────────────────────────────
    def analyze_text(self, text: str) -> Dict:
        """
        Full analysis of a piece of text.
        Returns: is_scam, scam_type, sentiment_score, risk_level, keywords,
                 latitude, longitude, location_name
        """
        text_clean = self._clean(text)

        # 1. Tourism relevance gate
        if not self._is_tourism_relevant(text_clean):
            return self._neutral_result()

        # 2. Scam type detection (keyword rules — always runs)
        scam_type, matched_keywords = self._detect_scam_type(text_clean)

        # 3. Is-scam classification
        is_scam = self._classify_scam(text_clean, scam_type)

        # 4. Sentiment score
        sentiment_score = self._get_sentiment(text_clean)

        # 5. Risk level
        risk_level = self._compute_risk(is_scam, sentiment_score, scam_type)

        # 6. DOUBLE VERIFICATION: AI Scope Check
        # If no scam type was found, we do a deep check to ensure it's not noise
        if not scam_type:
            if not self._verify_scope_deep(text_clean):
                return self._neutral_result()

        # 7. Location extraction (pass original title for title-match priority)
        lat, lon, location_name, geocode_confidence = self._extract_location(text_clean, title=text)

        return {
            "is_scam":            is_scam,
            "scam_type":          scam_type,
            "sentiment_score":    round(sentiment_score, 4),
            "risk_level":         risk_level,
            "keywords":           matched_keywords,
            "latitude":           lat,
            "longitude":          lon,
            "location_name":      location_name,
            "geocode_confidence": geocode_confidence,
        }

    # ── Internal methods ────────────────────────────────────────────────────
    @staticmethod
    def _clean(text: str) -> str:
        text = re.sub(r"http\S+", " ", text)          # remove URLs
        text = re.sub(r"[^\w\s.,!?'-]", " ", text)    # keep basic punctuation
        return text.lower().strip()

    def _is_tourism_relevant(self, text: str) -> bool:
        # Require a slightly stronger signal: at least one strong tourism word
        # or two general words
        strong_tourism = ["tourist", "traveler", "traveller", "backpacker", "hotel", "hostel", "tuk tuk", "guide", "safari", "foreigner"]
        count = sum(1 for kw in TOURISM_KEYWORDS if kw in text)
        has_strong = any(skw in text for skw in strong_tourism)
        
        # Avoid news about "Foreigners arrested" (Criminals vs Tourists)
        if "arrested" in text and ("center" in text or "ring" in text or "racket" in text):
            return False
            
        return has_strong or count >= 2

    def _verify_scope_deep(self, text: str) -> bool:
        """
        Tier 2 AI Verification: Confirms if the text is truly about a 
        tourist safety incident or just general news.
        """
        if not self._zero_shot:
            return True # Fallback if AI not available
            
        try:
            labels = ["Tourist Safety Incident", "General News", "Political News", "Crime by Foreigners"]
            res = self._zero_shot(text[:512], labels)
            top_label = res['labels'][0]
            top_score = res['scores'][0]
            
            # Must be Tourist Safety and at least 60% confident
            return top_label == "Tourist Safety Incident" and top_score > 0.60
        except:
            return True

    def _detect_scam_type(self, text: str):
        """Returns (scam_type | None, matched_keywords list)"""
        hits: Dict[str, int] = {}
        all_keywords = []

        # 1. Simple Keyword Matching
        for stype, keywords in SCAM_TAXONOMY.items():
            matched = [kw for kw in keywords if kw in text]
            if matched:
                hits[stype] = len(matched)
                all_keywords.extend(matched)

        if hits:
            top_type = max(hits, key=hits.get)
            return top_type, list(set(all_keywords))

        # 2. Powerful Zero-Shot AI Classification (Fallback)
        if self._zero_shot:
            try:
                # Include a "noise" label to catch non-tourism news
                candidate_labels = list(SCAM_TAXONOMY.keys()) + ["Domestic News", "Politics", "General Crime", "Sports"]
                result = self._zero_shot(text[:512], candidate_labels)
                top_label = result['labels'][0]
                top_score = result['scores'][0]
                
                # If it's a noise label, return None
                if top_label in ["Domestic News", "Politics", "General Crime", "Sports"]:
                    return None, []

                # If the AI is at least 30% confident in a scam label, assign it
                if top_score > 0.30:
                    return top_label, []
            except Exception as e:
                pass

        return None, []

    def _classify_scam(self, text: str, scam_type: Optional[str]) -> bool:
        # Rule-based signal: if we matched a scam type, it's a scam
        if scam_type:
            return True

        # Tier 1: sklearn model (if trained)
        if self._classifier:
            try:
                pred = self._classifier.predict([text])[0]
                return bool(pred)
            except Exception:
                pass

        # Fallback: negative sentiment + safety words
        safety_words = ["scam", "fraud", "ripped", "stolen", "danger",
                        "avoid", "warning", "unsafe", "harass"]
        return any(w in text for w in safety_words)

    def _get_sentiment(self, text: str) -> float:
        """Returns -1.0 (very negative) to +1.0 (very positive)"""
        # HuggingFace sentiment
        if self._sentiment_pipe:
            try:
                result = self._sentiment_pipe(text[:512])[0]
                label = result["label"].lower()
                score = result["score"]
                if "positive" in label:
                    return score
                elif "negative" in label:
                    return -score
                return 0.0
            except Exception:
                pass

        # TextBlob fallback
        if _TEXTBLOB_AVAILABLE:
            try:
                return TextBlob(text).sentiment.polarity
            except Exception:
                pass

        # Keyword-based fallback
        negative_words = ["scam", "terrible", "awful", "dangerous", "avoid",
                          "ripped", "fraud", "harass", "stolen", "dirty",
                          "overcharged", "fake", "worst"]
        positive_words = ["great", "wonderful", "safe", "friendly", "helpful",
                          "amazing", "beautiful", "recommend", "good"]
        neg = sum(1 for w in negative_words if w in text)
        pos = sum(1 for w in positive_words if w in text)
        total = neg + pos
        if total == 0:
            return 0.0
        return round((pos - neg) / total, 2)

    @staticmethod
    def _compute_risk(is_scam: bool, sentiment: float, scam_type) -> int:
        """1=Low, 2=Moderate, 3=High"""
        if not is_scam and sentiment >= 0:
            return 1
        if is_scam or sentiment < -0.5:
            # canonical scam type keys (lowercase_underscore) — these match CANONICAL_SCAM_TYPES
            if sentiment < -0.7 or scam_type in ("harassment", "unsafe_area", "gem_scam"):
                return 3
            return 2
        return 1

    @staticmethod
    def _extract_location(text: str, title: str = ""):
        """
        Returns (lat, lon, name, confidence) or (None, None, None, None).

        Geocoding bias fix — three rules over the original first-substring-wins:
          1. Prefer the LONGEST matching place name (avoids "Colombo" eating
             "Colombo Fort" when both appear).
          2. Require the match to appear in the title OR first ~500 chars of text
             before falling back to body-only matches.  A national advisory that
             mentions "Colombo" in paragraph 4 should not be pinned to Colombo.
          3. Return a geocode_confidence field so false-attribution rate can be
             quantified in the thesis rather than silently assumed away.

        confidence levels:
          "title_match"      — place found in the article title (highest quality)
          "first_200_words"  — place found in first ~500 chars of content
          "body_mention"     — place only found deeper in content (treat as national-scope;
                               exclude from weighted_evidence in district scoring)
        """
        title_lower = (title or "").lower()
        early_text  = text[:500].lower()
        full_text   = text.lower()

        best: dict | None = None

        # Sort longest-name first so longer, more specific names win
        for place, coords in sorted(SL_LOCATIONS.items(), key=lambda x: -len(x[0])):
            if place in title_lower:
                conf = "title_match"
            elif place in early_text:
                conf = "first_200_words"
            elif place in full_text:
                conf = "body_mention"
            else:
                continue

            # Prefer shorter confidence (title > early > body); on tie prefer longer name (already sorted)
            conf_rank = {"title_match": 0, "first_200_words": 1, "body_mention": 2}
            if best is None or conf_rank[conf] < conf_rank[best["conf"]]:
                best = {"lat": coords[0], "lon": coords[1], "name": place.title(), "conf": conf}

        if best:
            return best["lat"], best["lon"], best["name"], best["conf"]
        return None, None, None, None

    @staticmethod
    def _neutral_result() -> Dict:
        return {
            "is_scam":         False,
            "scam_type":       None,
            "sentiment_score": 0.0,
            "risk_level":      1,
            "keywords":        [],
            "latitude":        None,
            "longitude":       None,
            "location_name":   None,
        }
