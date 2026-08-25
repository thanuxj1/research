"""
Weather Recommendation Engine for Component 2 — Step 2.
Provides deterministic, explainable weather suitability scoring for Sri Lankan destinations.
"""

WEATHER_CONFIG = {
    "excellent_temp_min": 18.0,
    "excellent_temp_max": 24.0,
    "good_temp_max": 30.0,
    "moderate_temp_max": 33.0,
    "rain_excellent_max": 2.0,
    "rain_good_max": 5.0,
    "rain_moderate_max": 10.0,
    "rain_poor_max": 20.0
}

DESTINATION_WEATHER_PROFILES = {
    "Ella": {"category": "hiking", "rain_sensitivity": 1.3, "preferred_temp": (18.0, 26.0), "cool_tolerant": True},
    "Galle": {"category": "beach", "rain_sensitivity": 1.5, "preferred_temp": (24.0, 31.0), "cool_tolerant": False},
    "Sigiriya": {"category": "cultural", "rain_sensitivity": 0.9, "preferred_temp": (20.0, 32.0), "cool_tolerant": False},
    "Kandy": {"category": "cultural", "rain_sensitivity": 0.8, "preferred_temp": (20.0, 29.0), "cool_tolerant": True},
    "Nuwara Eliya": {"category": "mountain", "rain_sensitivity": 1.0, "preferred_temp": (13.0, 22.0), "cool_tolerant": True},
    "Mirissa": {"category": "beach", "rain_sensitivity": 1.5, "preferred_temp": (24.0, 31.0), "cool_tolerant": False},
    "Bentota": {"category": "beach", "rain_sensitivity": 1.5, "preferred_temp": (24.0, 31.0), "cool_tolerant": False},
    "Arugam Bay": {"category": "beach", "rain_sensitivity": 1.4, "preferred_temp": (25.0, 32.0), "cool_tolerant": False},
    "Anuradhapura": {"category": "cultural", "rain_sensitivity": 0.8, "preferred_temp": (22.0, 33.0), "cool_tolerant": False},
    "Polonnaruwa": {"category": "cultural", "rain_sensitivity": 0.8, "preferred_temp": (22.0, 33.0), "cool_tolerant": False},
    "Jaffna": {"category": "cultural", "rain_sensitivity": 0.8, "preferred_temp": (23.0, 34.0), "cool_tolerant": False},
    "Trincomalee": {"category": "beach", "rain_sensitivity": 1.4, "preferred_temp": (25.0, 33.0), "cool_tolerant": False},
    "Yala": {"category": "nature", "rain_sensitivity": 1.2, "preferred_temp": (22.0, 32.0), "cool_tolerant": False},
    "Hikkaduwa": {"category": "beach", "rain_sensitivity": 1.5, "preferred_temp": (24.0, 31.0), "cool_tolerant": False},
    "Dambulla": {"category": "cultural", "rain_sensitivity": 0.8, "preferred_temp": (21.0, 32.0), "cool_tolerant": False}
}


def calculate_weather_suitability(destination, temperature_c, rainfall_mm):
    """
    Calculates deterministic weather suitability for a destination based on expected temperature and rainfall.
    
    Returns:
    {
        "score": int (0-100),
        "condition": str ("Excellent"|"Good"|"Moderate"|"Poor"),
        "suitability": str ("excellent"|"good"|"moderate"|"poor"),
        "temperature_c": float,
        "rainfall_mm": float,
        "reasons": list[str]
    }
    """
    temp = float(temperature_c) if temperature_c is not null_check(temperature_c) else 26.0
    rain = float(rainfall_mm) if rainfall_mm is not null_check(rainfall_mm) else 2.0

    profile = DESTINATION_WEATHER_PROFILES.get(destination, {
        "category": "general", "rain_sensitivity": 1.0, "preferred_temp": (20.0, 30.0), "cool_tolerant": False
    })

    # A. Temperature Score
    cool_tolerant = profile.get("cool_tolerant", False)
    pref_min, pref_max = profile.get("preferred_temp", (20.0, 30.0))

    if cool_tolerant and temp < 18.0:
        temp_score = 95.0
    elif WEATHER_CONFIG["excellent_temp_min"] <= temp <= WEATHER_CONFIG["excellent_temp_max"]:
        temp_score = 100.0
    elif temp <= WEATHER_CONFIG["good_temp_max"]:
        temp_score = 85.0
    elif temp <= WEATHER_CONFIG["moderate_temp_max"]:
        temp_score = 65.0
    elif temp > WEATHER_CONFIG["moderate_temp_max"]:
        temp_score = 40.0
    else:
        temp_score = 60.0

    # B. Rainfall Score (Penalize heavy rain strongly)
    rain_sensitivity = profile.get("rain_sensitivity", 1.0)
    effective_rain = rain * rain_sensitivity

    if effective_rain <= WEATHER_CONFIG["rain_excellent_max"]:
        rain_score = 100.0
    elif effective_rain <= WEATHER_CONFIG["rain_good_max"]:
        rain_score = 80.0
    elif effective_rain <= WEATHER_CONFIG["rain_moderate_max"]:
        rain_score = 50.0
    elif effective_rain <= WEATHER_CONFIG["rain_poor_max"]:
        rain_score = 20.0
    else:
        rain_score = 0.0

    # C. Destination-Specific Score
    if pref_min <= temp <= pref_max and rain <= WEATHER_CONFIG["rain_good_max"]:
        dest_score = 100.0
    elif pref_min - 3 <= temp <= pref_max + 3 and rain <= WEATHER_CONFIG["rain_moderate_max"]:
        dest_score = 65.0
    else:
        dest_score = 25.0

    # Weighted Composite Score
    weighted = (temp_score * 0.45) + (rain_score * 0.40) + (dest_score * 0.15)
    final_score = int(round(min(100.0, max(0.0, weighted))))

    # Suitability & Condition
    if final_score >= 85:
        suitability = "excellent"
        condition = "Excellent"
    elif final_score >= 70:
        suitability = "good"
        condition = "Good"
    elif final_score >= 50:
        suitability = "moderate"
        condition = "Moderate"
    else:
        suitability = "poor"
        condition = "Poor"

    # Human-Readable Reasons
    reasons = []

    # Temperature reasons
    if temp > 33.0:
        reasons.append("High temperature may reduce outdoor comfort")
    elif temp < 18.0 and cool_tolerant:
        reasons.append("Cool temperature is suitable for this mountain destination")
    elif 18.0 <= temp <= 30.0:
        reasons.append("Comfortable temperature expected")
    elif temp < 18.0:
        reasons.append("Cooler temperature expected")
    else:
        reasons.append("Warm temperature expected")

    # Rainfall reasons
    category = profile.get("category", "general")
    if rain > 20.0:
        if category == "beach":
            reasons.append("Heavy rainfall may affect outdoor beach activities")
        elif category == "hiking":
            reasons.append("Heavy rainfall may disrupt outdoor hiking trails")
        else:
            reasons.append("Heavy rainfall expected")
    elif rain > 10.0:
        if category == "beach":
            reasons.append("Rainfall may affect beach activities")
        else:
            reasons.append("Moderate to heavy rainfall expected")
    elif rain > 5.0:
        reasons.append("Light to moderate rainfall expected")
    else:
        if category == "beach":
            reasons.append("Low rainfall makes beach activities ideal")
        elif category in ("hiking", "nature"):
            reasons.append("Low rainfall makes outdoor activities suitable")
        else:
            reasons.append("Low rainfall expected")

    return {
        "score": final_score,
        "condition": condition,
        "suitability": suitability,
        "temperature_c": round(temp, 1),
        "rainfall_mm": round(rain, 1),
        "reasons": reasons
    }


def null_check(val):
    return val is None
