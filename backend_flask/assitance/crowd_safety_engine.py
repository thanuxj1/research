"""
Crowd Level & Safety-Aware Event Engine for Component 2 — Step 4.
Provides deterministic crowd density scoring, safety benchmark analysis, and combined overall evaluation.
"""

DESTINATION_SAFETY_PROFILES = {
    "Ella": {"base_safety": 90, "level": "Very Safe", "notes": "Tourist-friendly mountain town"},
    "Galle": {"base_safety": 88, "level": "Safe", "notes": "Well-lit tourist fort & coastal area"},
    "Sigiriya": {"base_safety": 86, "level": "Safe", "notes": "Monitored UNESCO heritage site"},
    "Kandy": {"base_safety": 88, "level": "Safe", "notes": "Well-policed cultural heritage capital"},
    "Nuwara Eliya": {"base_safety": 92, "level": "Very Safe", "notes": "Very low crime, peaceful mountain environment"},
    "Mirissa": {"base_safety": 85, "level": "Safe", "notes": "Beach resort area"},
    "Bentota": {"base_safety": 86, "level": "Safe", "notes": "Resort coastal destination"},
    "Arugam Bay": {"base_safety": 82, "level": "Safe", "notes": "Relaxed surf beach"},
    "Anuradhapura": {"base_safety": 85, "level": "Safe", "notes": "Sacred historic city"},
    "Polonnaruwa": {"base_safety": 85, "level": "Safe", "notes": "Historical park area"},
    "Jaffna": {"base_safety": 78, "level": "Moderate", "notes": "Developing northern tourism area"},
    "Trincomalee": {"base_safety": 82, "level": "Safe", "notes": "East coast beach & harbor town"},
    "Yala": {"base_safety": 84, "level": "Safe", "notes": "National park guided safari environment"},
    "Hikkaduwa": {"base_safety": 82, "level": "Safe", "notes": "Lively beach area, watch nighttime crowds"},
    "Dambulla": {"base_safety": 85, "level": "Safe", "notes": "Cave temple complex"}
}


def classify_crowd_level(expected_crowd):
    """Classifies crowd density level based on visitor count telemetry."""
    val = float(expected_crowd) if expected_crowd is not None else 100.0
    if val < 110.0:
        return "Low"
    elif val < 160.0:
        return "Moderate"
    elif val < 210.0:
        return "High"
    else:
        return "Very High"


def calculate_crowd_score(expected_crowd, is_weekend=0):
    """
    Calculates deterministic crowd suitability score (0-100).
    Lower visitor count produces a higher suitability score.
    """
    val = float(expected_crowd) if expected_crowd is not None else 100.0
    
    if val < 80.0:
        base = 95.0
    elif val < 110.0:
        base = 88.0
    elif val < 160.0:
        base = 72.0
    elif val < 210.0:
        base = 50.0
    else:
        base = 30.0

    if is_weekend == 1 or is_weekend is True:
        base -= 5.0

    return int(round(min(100.0, max(0.0, base))))


def calculate_safety_score(destination, expected_crowd, transport_suitability="good"):
    """
    Calculates deterministic safety score (0-100) combining benchmark rating, crowd pressure, and transport access.
    """
    profile = DESTINATION_SAFETY_PROFILES.get(destination, {"base_safety": 85})
    base = float(profile["base_safety"])

    crowd_val = float(expected_crowd) if expected_crowd is not None else 100.0

    # Crowd pressure adjustment
    if crowd_val > 210.0:
        base -= 8.0
    elif crowd_val > 160.0:
        base -= 4.0

    # Transport access adjustment
    if transport_suitability in ("excellent", "good"):
        base += 3.0
    elif transport_suitability == "difficult":
        base -= 5.0

    return int(round(min(100.0, max(0.0, base))))


def classify_safety_level(safety_score):
    """Classifies safety level based on score."""
    score = int(safety_score)
    if score >= 88:
        return "Very Safe"
    elif score >= 75:
        return "Safe"
    elif score >= 60:
        return "Moderate"
    else:
        return "Caution"


def build_crowd_safety_summary(destination, expected_crowd, is_weekend=0, transport_suitability="good"):
    """
    Builds the complete crowd_safety summary object for a destination recommendation.
    """
    crowd_val = float(expected_crowd) if expected_crowd is not None else 100.0
    c_level = classify_crowd_level(crowd_val)
    c_score = calculate_crowd_score(crowd_val, is_weekend)

    s_score = calculate_safety_score(destination, crowd_val, transport_suitability)
    s_level = classify_safety_level(s_score)

    overall = int(round(c_score * 0.55 + s_score * 0.45))
    overall = min(100, max(0, overall))

    reasons = []
    warnings = []

    # Crowd reasons & warnings
    if c_level == "Low":
        reasons.append("Expected crowd level is low")
    elif c_level == "Moderate":
        reasons.append("Expected crowd level is moderate")
    elif c_level in ("High", "Very High"):
        warnings.append("Higher crowd levels may reduce comfort")

    if (is_weekend == 1 or is_weekend is True) and c_level in ("High", "Very High"):
        warnings.append("Additional caution is recommended during high-crowd weekend periods")

    # Safety reasons & warnings
    if s_level in ("Very Safe", "Safe"):
        reasons.append("Destination has a strong safety profile")
    elif s_level == "Moderate":
        reasons.append("Safety conditions are generally suitable for tourists")
    else:
        warnings.append("Exercise standard tourist safety precautions")

    # Transport interaction reason
    if transport_suitability in ("excellent", "good"):
        reasons.append("Transportation availability supports easier access")

    return {
        "crowd_score": c_score,
        "crowd_level": c_level,
        "expected_crowd": round(crowd_val, 1),
        "safety_score": s_score,
        "safety_level": s_level,
        "overall_score": overall,
        "reasons": reasons,
        "warnings": warnings
    }
