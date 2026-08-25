"""
Final AI Recommendation & Explainability Engine for Component 2 — Step 7 (FINAL STEP).
Combines outputs from Steps 1-6 into a single transparent score, decision level, ranking, trade-off analysis, and explainability advantages.
"""


def classify_decision_level(score):
    """Classifies recommendation score into decision level category."""
    val = int(round(score)) if score is not None else 85
    if val >= 90:
        return "Highly Recommended"
    elif val >= 80:
        return "Recommended"
    elif val >= 70:
        return "Suitable"
    elif val >= 60:
        return "Consider"
    else:
        return "Not Recommended"


def calculate_overall_score(pref_score=85, weather_score=85, transport_score=85, crowd_safety_score=85, activity_score=85, timing_score=85):
    """
    Calculates deterministic overall recommendation score (0-100) using a transparent weighted formula.
    Formula:
      0.20 * pref_score +
      0.15 * weather_score +
      0.15 * transport_score +
      0.20 * crowd_safety_score +
      0.15 * activity_score +
      0.15 * timing_score
    """
    p_s = float(pref_score) if pref_score is not None else 85.0
    w_s = float(weather_score) if weather_score is not None else 85.0
    t_s = float(transport_score) if transport_score is not None else 85.0
    cs_s = float(crowd_safety_score) if crowd_safety_score is not None else 85.0
    a_s = float(activity_score) if activity_score is not None else 85.0
    tm_s = float(timing_score) if timing_score is not None else 85.0

    weighted = (
        (p_s * 0.20) +
        (w_s * 0.15) +
        (t_s * 0.15) +
        (cs_s * 0.20) +
        (a_s * 0.15) +
        (tm_s * 0.15)
    )

    return int(round(min(100.0, max(0.0, weighted))))


def generate_why_recommended(destination, pref_score, weather_score, transport_score, crowd_safety_score, activity_score, timing_score):
    """Generates factor-backed explanations derived directly from sub-component scores."""
    reasons = []

    if pref_score >= 80:
        reasons.append("Strong match for your tourism preferences")
    if weather_score >= 80:
        reasons.append("Favorable weather conditions expected")
    if crowd_safety_score >= 80:
        reasons.append("Destination has a strong safety and crowd profile")
    if transport_score >= 80:
        reasons.append("Good transportation availability")
    if activity_score >= 80:
        reasons.append("Recommended activities match your interests")
    if timing_score >= 80:
        reasons.append("Recommended activity timing is feasible")

    if not reasons:
        reasons.append("Suitable overall destination for travel")

    return reasons


def identify_tradeoffs(destination, pref_score, weather_score, transport_score, crowd_safety_score, activity_score, timing_score, travel_time_hours=3.5, travel_time_str="3h 30m", crowd_level="Low"):
    """Identifies the weakest major factor for a destination to explain practical trade-offs."""
    tradeoffs = []

    factors = {
        "preference": float(pref_score),
        "weather": float(weather_score),
        "transport": float(transport_score),
        "crowd_safety": float(crowd_safety_score),
        "activity": float(activity_score),
        "timing": float(timing_score)
    }

    weakest_factor = min(factors, key=factors.get)
    min_val = factors[weakest_factor]

    if min_val < 85:
        if weakest_factor == "transport" and float(travel_time_hours) >= 3.0:
            tradeoffs.append(f"Travel time from Colombo is relatively long ({travel_time_str})")
        elif weakest_factor == "crowd_safety" and crowd_level in ("High", "Very High"):
            tradeoffs.append("Expected crowd level is higher than other recommended destinations")
        elif weakest_factor == "weather":
            tradeoffs.append("Weather conditions are less suitable for outdoor activities")
        elif weakest_factor == "transport":
            tradeoffs.append("Transportation availability is relatively limited")
        elif weakest_factor == "preference":
            tradeoffs.append("Fewer direct matches for specific preferred tags")
        elif weakest_factor == "timing":
            tradeoffs.append("Activity timing requires earlier departure")
        else:
            tradeoffs.append("Slight trade-off in travel duration")

    if not tradeoffs:
        tradeoffs.append("Minor trade-off in travel duration from primary transport hub")

    return tradeoffs


def generate_ai_advantages():
    """Generates explainability advantages highlighting multi-factor AI integration."""
    return [
        "Personalization derived from natural-language user preference matching",
        "Weather-aware suitability evaluation based on live Open-Meteo telemetry",
        "Travel-time and multi-modal transport availability modeling",
        "Crowd density prediction and safety benchmark risk assessment",
        "Deterministic activity matching and non-overlapping daily time scheduling"
    ]


def build_final_recommendation(place_item, rank_index, total_count):
    """
    Builds the final ai_recommendation summary object combining Steps 1-6 sub-component outputs.
    """
    pref_score = place_item.get("preference_match", {}).get("score", 85)
    w_score = place_item.get("weather_suitability", {}).get("score", 85)
    t_score = place_item.get("travel_transport", {}).get("transport_score", 85)
    cs_score = place_item.get("crowd_safety", {}).get("overall_score", 85)
    
    top_act = place_item.get("activity_recommendations", {}).get("top_activity", {})
    a_score = top_act.get("score", 85) if top_act else 85

    tm_score = place_item.get("event_timing", {}).get("timing_score", 85)

    overall_score = calculate_overall_score(
        pref_score=pref_score,
        weather_score=w_score,
        transport_score=t_score,
        crowd_safety_score=cs_score,
        activity_score=a_score,
        timing_score=tm_score
    )

    rank = rank_index + 1
    decision = classify_decision_level(overall_score)

    why_list = generate_why_recommended(
        destination=place_item.get("place", "Destination"),
        pref_score=pref_score,
        weather_score=w_score,
        transport_score=t_score,
        crowd_safety_score=cs_score,
        activity_score=a_score,
        timing_score=tm_score
    )

    travel_info = place_item.get("travel_transport", {})
    travel_time_h = travel_info.get("estimated_travel_time_hours", 3.5)
    travel_time_s = travel_info.get("estimated_travel_time", "3h 30m")
    c_level = place_item.get("crowd_safety", {}).get("crowd_level", "Low")

    tradeoff_list = identify_tradeoffs(
        destination=place_item.get("place", "Destination"),
        pref_score=pref_score,
        weather_score=w_score,
        transport_score=t_score,
        crowd_safety_score=cs_score,
        activity_score=a_score,
        timing_score=tm_score,
        travel_time_hours=travel_time_h,
        travel_time_str=travel_time_s,
        crowd_level=c_level
    )

    ai_adv_list = generate_ai_advantages()

    return {
        "overall_score": overall_score,
        "rank": rank,
        "decision": decision,
        "why_recommended": why_list,
        "tradeoffs": tradeoff_list,
        "ai_advantage": ai_adv_list
    }
