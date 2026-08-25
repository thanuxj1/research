from flask import Flask, Blueprint, request, jsonify
from pathlib import Path
import pandas as pd
import joblib
import requests

from weather_recommendation_engine import calculate_weather_suitability
from travel_transport_engine import build_travel_transport_summary
from crowd_safety_engine import build_crowd_safety_summary
from event_activity_engine import build_activity_recommendations
from event_timing_engine import build_event_timing_summary
from final_recommendation_engine import build_final_recommendation, calculate_overall_score

bp = Blueprint("assistance", __name__)

BASE_DIR = Path(__file__).resolve().parent

DESTINATIONS = [
    "Ella",
    "Galle",
    "Sigiriya",
    "Kandy",
    "Nuwara Eliya",
    "Mirissa",
    "Bentota",
    "Arugam Bay",
    "Anuradhapura",
    "Polonnaruwa",
    "Jaffna",
    "Trincomalee",
    "Yala",
    "Hikkaduwa",
    "Dambulla"
]

# Approximate city coordinates for live weather lookup
DESTINATION_COORDINATES = {
    "Ella": (6.8667, 81.0466),
    "Galle": (6.0535, 80.2210),
    "Sigiriya": (7.9570, 80.7603),
    "Kandy": (7.2906, 80.6337),
    "Nuwara Eliya": (6.9497, 80.7891),
    "Mirissa": (5.9483, 80.4716),
    "Bentota": (6.4218, 79.9950),
    "Arugam Bay": (6.8404, 81.8378),
    "Anuradhapura": (8.3114, 80.4037),
    "Polonnaruwa": (7.9403, 81.0188),
    "Jaffna": (9.6615, 80.0255),
    "Trincomalee": (8.5874, 81.2152),
    "Yala": (6.3725, 81.5185),
    "Hikkaduwa": (6.1407, 80.1010),
    "Dambulla": (7.8742, 80.6511)
}

# Destination profile tags for preference matching
DESTINATION_PROFILES = {
    "Ella": ["nature", "mountains", "cool_weather", "adventure", "hiking", "photography", "low_crowd"],
    "Galle": ["heritage", "cultural", "beach", "history", "photography", "food"],
    "Sigiriya": ["heritage", "cultural", "history", "photography", "adventure"],
    "Kandy": ["cultural", "heritage", "nature", "temple"],
    "Nuwara Eliya": ["cool_weather", "mountains", "nature", "relaxing", "photography", "low_crowd"],
    "Mirissa": ["beach", "relaxing", "food", "wildlife"],
    "Bentota": ["beach", "relaxing", "family"],
    "Arugam Bay": ["beach", "adventure", "relaxing"],
    "Anuradhapura": ["heritage", "cultural", "history", "temple"],
    "Polonnaruwa": ["heritage", "cultural", "history"],
    "Jaffna": ["cultural", "heritage", "food", "history"],
    "Trincomalee": ["beach", "heritage", "relaxing", "nature"],
    "Yala": ["wildlife", "nature", "adventure", "photography", "low_crowd"],
    "Hikkaduwa": ["beach", "relaxing", "food"],
    "Dambulla": ["heritage", "cultural", "temple", "history"]
}

# Destination descriptions for backward compatibility
DESTINATION_DESCRIPTIONS = {
    "Ella": "Beautiful mountain town with waterfalls, tea plantations and scenic views.",
    "Galle": "Historic coastal city with Dutch architecture, beaches and rich culture.",
    "Sigiriya": "Ancient rock fortress and UNESCO World Heritage Site.",
    "Kandy": "Cultural capital with sacred Temple of the Tooth and royal botanical gardens.",
    "Nuwara Eliya": "Little England of Sri Lanka with cool climate and tea estates.",
    "Mirissa": "Relaxing beach destination famous for whale watching and surf breaks.",
    "Bentota": "Prime beach resort town known for water sports, lagoons, and golden sands.",
    "Arugam Bay": "World-famous surfing haven on the east coast with relaxed beach vibes.",
    "Anuradhapura": "Sacred ancient capital with magnificent stupas, ruins, and holy Bodhi tree.",
    "Polonnaruwa": "Royal medieval kingdom with preserved stone temples and Buddha statues.",
    "Jaffna": "Cultural heart of northern Sri Lanka with colorful Kovils and unique cuisine.",
    "Trincomalee": "Deep natural harbor with Nilaveli beaches and Koneswaram Hindu temple.",
    "Yala": "Sri Lanka’s premier wildlife national park, world-renowned for leopard sightings.",
    "Hikkaduwa": "Lively southern beach town popular for coral reefs, turtles, and nightlife.",
    "Dambulla": "Famous Golden Cave Temple complex filled with ancient Buddhist murals."
}

PREFERENCE_KEYWORDS = {
    "nature": ["nature", "scenery", "green", "waterfall", "botanical"],
    "beach": ["beach", "coast", "sea", "ocean", "sand", "coastal", "surf", "beachside"],
    "wildlife": ["wildlife", "safari", "leopard", "animals", "national park", "yala"],
    "adventure": ["adventure", "hiking", "hike", "trekking", "rafting", "climbing"],
    "cultural": ["cultural", "culture", "tradition", "temple", "kovil", "festival"],
    "heritage": ["heritage", "history", "historical", "ancient", "unesco", "fort", "ruins"],
    "mountains": ["mountain", "mountains", "hill", "highlands", "peak"],
    "cool_weather": ["cool weather", "cool-weather", "cool", "misty", "cold", "cold place", "cool place", "cold weather", "chilly", "cold climate"],
    "relaxing": ["relaxing", "relax", "calm"],
    "low_crowd": ["low crowd", "less crowd", "quiet", "peaceful", "avoid crowd", "uncrowded", "low-crowd", "quiet place", "peaceful place", "low crowds", "peaceful destination", "quiet destination", "low crowd place", "low crowds place"],
    "family": ["family", "kids", "children"],
    "photography": ["photography", "photo", "scenic", "view"],
    "food": ["food", "cuisine", "dining", "seafood"],
    "hiking": ["hiking", "hike", "trail", "trekking"]
}

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# ----------------------------
# Load models
# ----------------------------
rf_crowd = joblib.load(BASE_DIR / "crowd.pkl")
rf_weather = joblib.load(BASE_DIR / "random_forest_weather_model.pkl")

crowd_columns = joblib.load(BASE_DIR / "crowd_columns.pkl")
weather_columns = joblib.load(BASE_DIR / "weather_columns.pkl")


def parse_user_preferences(text: str):
    """Deterministically extracts user tourism intent categories from natural language input."""
    if not text or not isinstance(text, str):
        return []
    t = text.lower()
    extracted = []
    for pref, keywords in PREFERENCE_KEYWORDS.items():
        if any(kw in t for kw in keywords):
            if pref not in extracted:
                extracted.append(pref)
    return extracted


def parse_user(text):
    """Backward compatible user text parser."""
    text_str = text.lower() if isinstance(text, str) else ""
    return {
        "prefer_low_crowd": "low crowd" in text_str or "less crowd" in text_str or "quiet" in text_str or "peaceful" in text_str,
        "preferences": parse_user_preferences(text_str)
    }


def get_live_weather_features(location):
    coords = DESTINATION_COORDINATES.get(location)
    if not coords:
        return {}

    lat, lon = coords
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation",
        "daily": "uv_index_max",
        "timezone": "auto",
        "forecast_days": 1
    }

    try:
        response = requests.get(OPEN_METEO_FORECAST_URL, params=params, timeout=8)
        response.raise_for_status()

        payload = response.json()
        current = payload.get("current", {})
        daily = payload.get("daily", {})

        time_value = current.get("time")
        if time_value:
            dt = pd.to_datetime(time_value)
        else:
            dt = pd.Timestamp.now()

        uv_values = daily.get("uv_index_max", [6])
        uv_index = float(uv_values[0]) if uv_values else 6.0

        return {
            "month": int(dt.month),
            "day_of_week": int(dt.dayofweek),
            "is_weekend": int(dt.dayofweek >= 5),
            "rainfall_mm": float(current.get("precipitation", 2.0)),
            "temperature_c": float(current.get("temperature_2m", 28.5)),
            "humidity": float(current.get("relative_humidity_2m", 75)),
            "wind_speed": float(current.get("wind_speed_10m", 10)),
            "uv_index": uv_index
        }
    except (requests.RequestException, ValueError, TypeError, IndexError):
        return {}


def predict_crowd(location, crowd_input):
    sample = crowd_input.copy()

    # defaults
    sample.setdefault("month", 7)
    sample.setdefault("day_of_week", 2)
    sample.setdefault("is_weekend", 0)
    sample.setdefault("lag_1", 100)
    sample.setdefault("lag_2", 100)
    sample.setdefault("lag_3", 100)

    location_factor = {
        "Ella": -20,
        "Galle": 10,
        "Sigiriya": 30,
        "Kandy": 15
    }

    base = location_factor.get(location, 0)

    sample["lag_1"] += base
    sample["lag_2"] += base
    sample["lag_3"] += base

    for col in crowd_columns:
        if "location_" in col:
            sample[col] = 1 if col == f"location_{location}" else 0

    df = pd.DataFrame([sample])
    df = df.reindex(columns=crowd_columns, fill_value=0)

    return float(rf_crowd.predict(df)[0])


def predict_weather(location, weather_input):
    sample = weather_input.copy()

    sample.setdefault("month", 7)
    sample.setdefault("day_of_week", 2)
    sample.setdefault("is_weekend", 0)
    sample.setdefault("rainfall_mm", 2.0)
    sample.setdefault("temperature_c", 28.5)
    sample.setdefault("humidity", 75)
    sample.setdefault("wind_speed", 10)
    sample.setdefault("uv_index", 6)

    if location in ["Ella", "Kandy"]:
        sample["rainfall_mm"] += 3
    elif location in ["Sigiriya"]:
        sample["temperature_c"] += 2
    elif location in ["Galle"]:
        sample["humidity"] += 5

    for col in weather_columns:
        if "location_" in col:
            sample[col] = 1 if col == f"location_{location}" else 0
        if "weather_condition_" in col:
            sample[col] = 0

    if sample["rainfall_mm"] > 8:
        sample["weather_condition_rainy"] = 1
    elif sample["rainfall_mm"] > 3:
        sample["weather_condition_cloudy"] = 1
    else:
        sample["weather_condition_sunny"] = 1

    df = pd.DataFrame([sample])
    df = df.reindex(columns=weather_columns, fill_value=0)

    pred = rf_weather.predict(df)[0]

    return {0: "Good", 1: "Moderate", 2: "Poor"}[pred]


def calculate_preference_match_and_reasons(place, user_preferences, crowd_val, weather_val):
    """Computes preference matching metadata and factor-based recommendation explanations."""
    dest_tags = DESTINATION_PROFILES.get(place, [])
    matched_tags = []

    for pref in user_preferences:
        if pref in dest_tags:
            matched_tags.append(pref)
        elif pref == "low_crowd" and crowd_val < 120:
            matched_tags.append(pref)

    # Compute preference match score
    if user_preferences:
        match_score = int(round((len(matched_tags) / len(user_preferences)) * 100.0))
        match_score = min(100, max(0, match_score))
    else:
        match_score = 85

    reasons = []
    
    # Generate explanations strictly derived from actual scoring factors
    for tag in matched_tags:
        if tag == "nature":
            reasons.append("Matches your nature preference")
        elif tag == "beach":
            reasons.append("Matches your beach preference")
        elif tag == "wildlife":
            reasons.append("Matches your wildlife preference")
        elif tag == "adventure":
            reasons.append("Matches your adventure preference")
        elif tag == "cultural":
            reasons.append("Matches your cultural preference")
        elif tag == "heritage":
            reasons.append("Matches your heritage preference")
        elif tag == "cool_weather":
            reasons.append("Suitable for cool-weather preferences")
        elif tag == "mountains":
            reasons.append("Matches your mountain preference")
        elif tag == "relaxing":
            reasons.append("Ideal for a relaxing getaway")
        elif tag == "low_crowd":
            reasons.append("Matches your low crowd / quiet preference")
        elif tag == "family":
            reasons.append("Great for family travel")
        elif tag == "photography":
            reasons.append("Offers great scenic views for photography")
        elif tag == "food":
            reasons.append("Renowned for local food and dining")
        elif tag == "hiking":
            reasons.append("Great for hiking and outdoor trails")

    if crowd_val < 110 or "low_crowd" in user_preferences:
        if "Expected crowd level is low" not in reasons:
            reasons.append("Expected crowd level is low")

    if weather_val in ("Good", "Excellent", "Low"):
        if "Favorable weather conditions expected" not in reasons:
            reasons.append("Favorable weather conditions expected")

    if not reasons:
        reasons.append("Top recommended Sri Lankan destination")

    return {
        "preference_match": {
            "matched": matched_tags,
            "score": match_score
        },
        "recommendation_reason": reasons
    }


def calculate_score(crowd, weather, user_preferences, place, pref_match_score=85, weather_score=85, transport_score=85, crowd_safety_score=85, activity_score=85, timing_score=85):
    """Calculates overall AI recommendation score (0-100) using deterministic weighted formula."""
    return calculate_overall_score(
        pref_score=pref_match_score,
        weather_score=weather_score,
        transport_score=transport_score,
        crowd_safety_score=crowd_safety_score,
        activity_score=activity_score,
        timing_score=timing_score
    )


@bp.route("/recommend", methods=["POST"])
def recommend():
    data = request.json or {}

    user_text = data.get("user_text", "")
    weather_override = data.get("weather", {})
    crowd_input = data.get("crowd", {})
    origin_input = data.get("origin", "Colombo")
    transport_mode_input = data.get("transport_mode", "car")

    if not isinstance(weather_override, dict):
        weather_override = {}
    if not isinstance(crowd_input, dict):
        crowd_input = {}

    user_preferences = parse_user_preferences(user_text)

    raw_results = []

    for place in DESTINATIONS:
        live_weather = get_live_weather_features(place)
        weather_input = {**live_weather, **weather_override}

        # Extract numeric weather parameters
        temp_c = float(weather_input.get("temperature_c", 28.5))
        rain_mm = float(weather_input.get("rainfall_mm", 2.0))

        # Compute Step 2 weather suitability
        weather_suitability = calculate_weather_suitability(place, temp_c, rain_mm)

        # Compute Step 3 travel & transport summary
        travel_transport = build_travel_transport_summary(
            origin=origin_input,
            destination=place,
            transport_mode=transport_mode_input
        )

        crowd = predict_crowd(place, crowd_input)
        raw_weather_pred = predict_weather(place, weather_input)
        weather_display = weather_suitability.get("condition", raw_weather_pred)

        # Compute Step 4 crowd & safety summary
        is_weekend_val = crowd_input.get("is_weekend", 0)
        crowd_safety = build_crowd_safety_summary(
            destination=place,
            expected_crowd=crowd,
            is_weekend=is_weekend_val,
            transport_suitability=travel_transport.get("suitability", "good")
        )

        # Compute Step 5 event & activity recommendations
        activity_recommendations = build_activity_recommendations(
            destination=place,
            user_preferences=user_preferences,
            weather_suitability=weather_suitability,
            travel_transport=travel_transport,
            crowd_safety=crowd_safety
        )

        # Compute Step 6 event timing & daily scheduling
        event_timing = build_event_timing_summary(
            destination=place,
            activities=activity_recommendations,
            travel_transport=travel_transport,
            weather_suitability=weather_suitability,
            crowd_safety=crowd_safety
        )

        match_and_reasons = calculate_preference_match_and_reasons(place, user_preferences, crowd, weather_display)
        p_match_score = match_and_reasons["preference_match"]["score"]
        w_score = weather_suitability.get("score", 85)
        t_score = travel_transport.get("transport_score", 85)
        cs_score = crowd_safety.get("overall_score", 85)
        
        top_act = activity_recommendations.get("top_activity")
        act_score = top_act.get("score", 85) if top_act else 85
        tm_score = event_timing.get("timing_score", 85)

        score = calculate_score(
            crowd=crowd,
            weather=weather_display,
            user_preferences=user_preferences,
            place=place,
            pref_match_score=p_match_score,
            weather_score=w_score,
            transport_score=t_score,
            crowd_safety_score=cs_score,
            activity_score=act_score,
            timing_score=tm_score
        )

        # Extend recommendation_reason without duplicates
        reasons_list = list(match_and_reasons["recommendation_reason"])

        for w_reason in weather_suitability.get("reasons", []):
            if w_reason not in reasons_list:
                reasons_list.append(w_reason)

        for t_reason in travel_transport.get("reasons", []):
            if t_reason not in reasons_list:
                reasons_list.append(t_reason)

        for cs_reason in crowd_safety.get("reasons", []):
            if cs_reason not in reasons_list:
                reasons_list.append(cs_reason)

        # Add top activity reason if available
        if top_act and top_act.get("name"):
            act_msg = f"Top activity match: {top_act['name']}"
            if act_msg not in reasons_list:
                reasons_list.append(act_msg)

        # Add optimal activity timing reason
        if event_timing.get("best_activity_time"):
            timing_msg = f"Optimal activity window: {event_timing['best_activity_time']} ({event_timing['best_time_period']})"
            if timing_msg not in reasons_list:
                reasons_list.append(timing_msg)

        crowd_label = "Low" if crowd < 110 else "Moderate" if crowd < 200 else "High"
        description = DESTINATION_DESCRIPTIONS.get(place, "Top travel destination in Sri Lanka.")

        raw_results.append({
            "place": place,
            "score": score,
            "crowd": round(crowd, 2),
            "crowd_label": crowd_label,
            "weather": weather_display,
            "desc": description,
            "preference_match": match_and_reasons["preference_match"],
            "recommendation_reason": reasons_list,
            "weather_suitability": weather_suitability,
            "travel_transport": travel_transport,
            "crowd_safety": crowd_safety,
            "activity_recommendations": activity_recommendations,
            "event_timing": event_timing
        })

    # Sort deterministically by overall recommendation score
    pre_sorted = sorted(
        raw_results,
        key=lambda item: (
            item["preference_match"]["score"] * 0.20 +
            item["weather_suitability"]["score"] * 0.15 +
            item["travel_transport"]["transport_score"] * 0.15 +
            item["crowd_safety"]["overall_score"] * 0.20 +
            (item["activity_recommendations"]["top_activity"]["score"] if item["activity_recommendations"].get("top_activity") else 85) * 0.15 +
            item["event_timing"]["timing_score"] * 0.15
        ),
        reverse=True
    )

    final_results = []
    total_count = len(pre_sorted)

    for r_idx, item in enumerate(pre_sorted):
        ai_rec = build_final_recommendation(item, r_idx, total_count)
        item["ai_recommendation"] = ai_rec
        item["score"] = ai_rec["overall_score"]  # Sync primary score
        final_results.append(item)

    return jsonify({
        "recommendations": final_results
    })


@bp.route("/predict", methods=["POST"])
def predict():
    return recommend()


if __name__ == "__main__":
    app = Flask(__name__)
    app.register_blueprint(bp)
    app.run(debug=True)