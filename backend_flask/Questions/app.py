from flask import Flask, Blueprint, request, jsonify
from pathlib import Path
import joblib
import json
import re

bp = Blueprint("questions", __name__)

BASE_DIR = Path(__file__).resolve().parent

# =====================================================
# LOAD MODEL
# =====================================================

MODEL_PATH = "naive_bayes_model.pkl"

model = joblib.load(BASE_DIR / MODEL_PATH)

print("✅ Naive Bayes model loaded")


# =====================================================
# LOAD KNOWLEDGE BASE
# =====================================================

JSON_PATH = "cultural_knowledge.json"

with open(BASE_DIR / JSON_PATH, "r", encoding="utf-8") as f:
    cultural_data = json.load(f)

print("✅ Cultural knowledge base loaded")


# =====================================================
# SETTINGS
# =====================================================

CONFIDENCE_THRESHOLD = 0.45

# The trained classifier was fit on a tiny, narrow dataset and is unreliable
# even within the intents it knows (e.g. "Etiquette for locals" returns
# "unknown"; "What should I wear when visiting a temple?" returns
# "festival_guidance"). It also has no "unknown" class, so anything outside
# its 5 intents (like travel-timing or food questions) gets forced into
# whichever bucket scores highest, often with misleadingly high confidence.
#
# Since retraining isn't currently an option, intent detection is handled by
# keyword rules first — one per intent, checked in the order below (most
# specific/narrow vocabulary first, broadest last so it doesn't shadow the
# others). The ML model is only consulted as a fallback for questions that
# don't match any rule.
INTENT_RULES = [
    ("language_phrase", [
        r"\bphrase\b", r"\blanguage\b", r"\bsinhala\b", r"\btamil\b",
        r"\bgreeting\b", r"\btranslat\w*\b", r"how (do|can) (i|you) say",
        r"\bsay hello\b",
    ]),
    ("photography_rules", [
        r"\bphoto\w*\b", r"\bpictures?\b", r"\bcamera\b", r"\bselfie\w*\b",
        r"\bdrone\w*\b", r"\bfilming\b", r"\bvideo\s*record\w*\b",
    ]),
    ("festival_guidance", [
        r"\bfestival\w*\b", r"\bperahera\b", r"\bvesak\b", r"\bpongal\b",
        r"\bprocession\w*\b", r"\bcelebrat\w*\b", r"\bnew year\b",
    ]),
    ("travel_timing", [
        r"\bbest\s+(time|season|month)s?\b.*\bvisit\b",
        r"\bwhen\b.*\b(should|to|can)\b.*\bvisit\b",
        r"\bwhich\s+(season|month)s?\b",
        r"\bgood\s+time\b.*\bvisit\b",
        r"\bmonsoon\s+season\b",
        r"\bweather\b.*\bvisit\b",
    ]),
    ("local_food", [
        r"\bfood\w*\b", r"\bcuisine\w*\b", r"\bdish\w*\b", r"\beat\w*\b",
        r"\bmeals?\b", r"\bcurry\b", r"\brestaurants?\b",
    ]),
    ("dress_code", [
        r"\bwear\w*\b", r"\bclothing\b", r"\bclothes\b", r"\bdress\s*code\b",
        r"\boutfit\b", r"\battire\b", r"\bshorts\b", r"\bskirts?\b",
        r"\bsleeveless\b",
    ]),
    ("etiquette", [
        r"\betiquette\b", r"\bmanners\b", r"\bbehav\w*\b",
        r"\bremove.*shoes\b", r"\bpoint.*feet\b", r"\btouch.*monks?\b",
        r"\bcustoms?\b",
    ]),
]

INTENT_RULES = [
    (intent, re.compile("|".join(patterns), re.IGNORECASE))
    for intent, patterns in INTENT_RULES
]


def match_rule_based_intent(question):
    for intent, pattern in INTENT_RULES:
        if pattern.search(question):
            return intent
    return None


# =====================================================
# HOME ROUTE
# =====================================================

@bp.route("/")
def home():

    return jsonify({
        "success": True,
        "message": "Sri Lanka Cultural Intelligence API Running"
    })


# =====================================================
# HEALTH CHECK
# =====================================================

@bp.route("/health")
def health():

    return jsonify({
        "status": "healthy"
    })


# =====================================================
# PREDICT ROUTE
# =====================================================

@bp.route("/predict", methods=["POST"])
def predict():

    try:

        data = request.get_json()

        # =============================================
        # VALIDATE INPUT
        # =============================================

        if not data:
            return jsonify({
                "success": False,
                "error": "JSON body is required"
            }), 400

        question = data.get("question", "").strip()

        if question == "":
            return jsonify({
                "success": False,
                "error": "Question is required"
            }), 400

        # =============================================
        # BASIC GIBBERISH CHECK
        # =============================================

        # Minimum length
        if len(question) < 3:

            return jsonify({
                "success": True,
                "question": question,
                "predicted_intent": "unknown",
                "confidence": 0.0,
                "response": {
                    "title": "Unknown Input",
                    "description": "Input is too short.",
                    "guidance": [
                        "Please enter a meaningful cultural or tourism-related question."
                    ]
                }
            })

        # Must contain letters
        if not re.search(r"[a-zA-Z]", question):

            return jsonify({
                "success": True,
                "question": question,
                "predicted_intent": "unknown",
                "confidence": 0.0,
                "response": {
                    "title": "Unknown Input",
                    "description": "No valid text detected.",
                    "guidance": [
                        "Please enter a readable question."
                    ]
                }
            })

        # Too many special characters
        special_char_ratio = len(
            re.findall(r"[^a-zA-Z0-9\s]", question)
        ) / len(question)

        if special_char_ratio > 0.5:

            return jsonify({
                "success": True,
                "question": question,
                "predicted_intent": "unknown",
                "confidence": 0.0,
                "response": {
                    "title": "Unknown Input",
                    "description": "Input appears invalid or noisy.",
                    "guidance": [
                        "Please enter a proper tourism or cultural question."
                    ]
                }
            })

        # =============================================
        # RULE-BASED INTENT MATCH (primary — the ML
        # model is unreliable, see INTENT_RULES comment)
        # =============================================

        rule_intent = match_rule_based_intent(question)

        if rule_intent is not None:

            return jsonify({
                "success": True,
                "question": question,
                "predicted_intent": rule_intent,
                "confidence": 1.0,
                "response": cultural_data.get(rule_intent, {
                    "title": "No Data",
                    "description": "No cultural guidance available."
                })
            })

        # =============================================
        # PREDICT PROBABILITIES (fallback for questions
        # no keyword rule recognized)
        # =============================================

        probabilities = model.predict_proba([question])[0]

        max_prob = float(max(probabilities))

        best_index = probabilities.argmax()

        predicted_intent = model.classes_[best_index]

        # =============================================
        # CONFIDENCE THRESHOLD
        # =============================================

        if max_prob < CONFIDENCE_THRESHOLD:

            predicted_intent = "unknown"

            response_data = {
                "title": "Unknown Question",
                "description": "The system could not understand the question.",
                
            }

        else:

            response_data = cultural_data.get(
                predicted_intent,
                {
                    "title": "No Data",
                    "description": "No cultural guidance available."
                }
            )

        # =============================================
        # FINAL RESPONSE
        # =============================================

        return jsonify({

            "success": True,

            "question": question,

            "predicted_intent": predicted_intent,

            "confidence": round(max_prob, 4),

            "response": response_data

        })

    except Exception as e:

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# =====================================================
# RUN SERVER
# =====================================================

if __name__ == "__main__":

    app = Flask(__name__)
    app.register_blueprint(bp)
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )