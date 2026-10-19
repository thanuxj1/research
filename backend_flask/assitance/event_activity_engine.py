"""
Event & Activity Matching Engine for Component 2 — Step 5.
Provides research-benchmark activity datasets and deterministic activity scoring & ranking.
"""

DESTINATION_ACTIVITIES = {
    "Nuwara Eliya": [
        {
            "name": "Tea Estate & Factory Visit",
            "categories": ["nature", "cool_weather", "photography"],
            "weather_sensitivity": "medium",
            "rain_tolerance": "medium",
            "crowd_tolerance": "high",
            "safety_requirement": "medium",
            "typical_duration_hours": 2,
            "best_time": "morning"
        },
        {
            "name": "Horton Plains & World's End Hiking",
            "categories": ["nature", "hiking", "adventure"],
            "weather_sensitivity": "high",
            "rain_tolerance": "low",
            "crowd_tolerance": "medium",
            "safety_requirement": "high",
            "typical_duration_hours": 4,
            "best_time": "early_morning"
        },
        {
            "name": "Gregory Lake Park & Boating",
            "categories": ["relaxing", "family", "cool_weather"],
            "weather_sensitivity": "medium",
            "rain_tolerance": "medium",
            "crowd_tolerance": "high",
            "safety_requirement": "low",
            "typical_duration_hours": 2,
            "best_time": "afternoon"
        },
        {
            "name": "Victoria Park Botanical Walk",
            "categories": ["nature", "photography", "relaxing"],
            "weather_sensitivity": "medium",
            "rain_tolerance": "medium",
            "crowd_tolerance": "high",
            "safety_requirement": "low",
            "typical_duration_hours": 1.5,
            "best_time": "morning"
        }
    ],

    "Kandy": [
        {
            "name": "Temple of the Tooth Relic Visit",
            "categories": ["cultural", "heritage", "temple"],
            "weather_sensitivity": "low",
            "rain_tolerance": "high",
            "crowd_tolerance": "medium",
            "safety_requirement": "high",
            "typical_duration_hours": 2,
            "best_time": "morning"
        },
        {
            "name": "Royal Botanical Gardens Peradeniya",
            "categories": ["nature", "photography", "relaxing"],
            "weather_sensitivity": "high",
            "rain_tolerance": "medium",
            "crowd_tolerance": "high",
            "safety_requirement": "medium",
            "typical_duration_hours": 3,
            "best_time": "morning"
        },
        {
            "name": "Kandy Lake Promenade",
            "categories": ["relaxing", "photography"],
            "weather_sensitivity": "medium",
            "rain_tolerance": "medium",
            "crowd_tolerance": "high",
            "safety_requirement": "low",
            "typical_duration_hours": 1,
            "best_time": "evening"
        },
        {
            "name": "Kandy Cultural Dance Performance",
            "categories": ["cultural", "family"],
            "weather_sensitivity": "low",
            "rain_tolerance": "high",
            "crowd_tolerance": "high",
            "safety_requirement": "low",
            "typical_duration_hours": 1.5,
            "best_time": "evening"
        }
    ],

    "Ella": [
        {
            "name": "Nine Arches Bridge Visit",
            "categories": ["photography", "heritage", "nature"],
            "weather_sensitivity": "high",
            "rain_tolerance": "low",
            "crowd_tolerance": "medium",
            "safety_requirement": "medium",
            "typical_duration_hours": 2,
            "best_time": "morning"
        },
        {
            "name": "Little Adam's Peak Hiking",
            "categories": ["hiking", "nature", "adventure"],
            "weather_sensitivity": "high",
            "rain_tolerance": "low",
            "crowd_tolerance": "medium",
            "safety_requirement": "medium",
            "typical_duration_hours": 2.5,
            "best_time": "early_morning"
        },
        {
            "name": "Ella Rock Trekking",
            "categories": ["hiking", "adventure", "nature"],
            "weather_sensitivity": "high",
            "rain_tolerance": "low",
            "crowd_tolerance": "medium",
            "safety_requirement": "high",
            "typical_duration_hours": 4,
            "best_time": "early_morning"
        },
        {
            "name": "Ravana Waterfalls & Cave",
            "categories": ["nature", "adventure"],
            "weather_sensitivity": "high",
            "rain_tolerance": "low",
            "crowd_tolerance": "high",
            "safety_requirement": "medium",
            "typical_duration_hours": 1.5,
            "best_time": "afternoon"
        }
    ],

    "Galle": [
        {
            "name": "Galle Fort Heritage Walk",
            "categories": ["heritage", "cultural", "history", "photography"],
            "weather_sensitivity": "medium",
            "rain_tolerance": "medium",
            "crowd_tolerance": "high",
            "safety_requirement": "medium",
            "typical_duration_hours": 2.5,
            "best_time": "afternoon"
        },
        {
            "name": "Galle Lighthouse & Bastion Sunset",
            "categories": ["photography", "relaxing", "beach"],
            "weather_sensitivity": "medium",
            "rain_tolerance": "medium",
            "crowd_tolerance": "high",
            "safety_requirement": "low",
            "typical_duration_hours": 1,
            "best_time": "evening"
        },
        {
            "name": "Unawatuna Beach Relaxation",
            "categories": ["beach", "relaxing", "food"],
            "weather_sensitivity": "high",
            "rain_tolerance": "low",
            "crowd_tolerance": "high",
            "safety_requirement": "low",
            "typical_duration_hours": 3,
            "best_time": "afternoon"
        }
    ],

    "Sigiriya": [
        {
            "name": "Sigiriya Rock Fortress Climb",
            "categories": ["heritage", "history", "adventure", "photography"],
            "weather_sensitivity": "high",
            "rain_tolerance": "low",
            "crowd_tolerance": "medium",
            "safety_requirement": "high",
            "typical_duration_hours": 3,
            "best_time": "early_morning"
        },
        {
            "name": "Pidurangala Rock Sunrise Trek",
            "categories": ["hiking", "adventure", "photography"],
            "weather_sensitivity": "high",
            "rain_tolerance": "low",
            "crowd_tolerance": "medium",
            "safety_requirement": "high",
            "typical_duration_hours": 2.5,
            "best_time": "early_morning"
        }
    ],

    "Mirissa": [
        {
            "name": "Whale & Dolphin Watching Safari",
            "categories": ["wildlife", "ocean", "adventure"],
            "weather_sensitivity": "high",
            "rain_tolerance": "low",
            "crowd_tolerance": "medium",
            "safety_requirement": "high",
            "typical_duration_hours": 4,
            "best_time": "early_morning"
        },
        {
            "name": "Mirissa Beach & Coconut Tree Hill",
            "categories": ["beach", "photography", "relaxing"],
            "weather_sensitivity": "high",
            "rain_tolerance": "low",
            "crowd_tolerance": "high",
            "safety_requirement": "low",
            "typical_duration_hours": 2,
            "best_time": "evening"
        }
    ],

    "Bentota": [
        {
            "name": "Bentota River Water Sports & Jet Ski",
            "categories": ["adventure", "beach", "family"],
            "weather_sensitivity": "high",
            "rain_tolerance": "low",
            "crowd_tolerance": "medium",
            "safety_requirement": "high",
            "typical_duration_hours": 2.5,
            "best_time": "morning"
        },
        {
            "name": "Maduganga River Mangrove Safari",
            "categories": ["nature", "wildlife", "family"],
            "weather_sensitivity": "medium",
            "rain_tolerance": "medium",
            "crowd_tolerance": "high",
            "safety_requirement": "medium",
            "typical_duration_hours": 2,
            "best_time": "morning"
        }
    ],

    "Arugam Bay": [
        {
            "name": "Arugam Bay Surf Session",
            "categories": ["beach", "adventure", "surf"],
            "weather_sensitivity": "high",
            "rain_tolerance": "low",
            "crowd_tolerance": "medium",
            "safety_requirement": "high",
            "typical_duration_hours": 3,
            "best_time": "morning"
        },
        {
            "name": "Kudumbigala Monastery Trek",
            "categories": ["heritage", "nature", "hiking"],
            "weather_sensitivity": "medium",
            "rain_tolerance": "medium",
            "crowd_tolerance": "high",
            "safety_requirement": "medium",
            "typical_duration_hours": 2.5,
            "best_time": "early_morning"
        }
    ],

    "Anuradhapura": [
        {
            "name": "Ruwanwelisaya & Sacred Bodhi Tree Tour",
            "categories": ["cultural", "heritage", "temple", "history"],
            "weather_sensitivity": "medium",
            "rain_tolerance": "medium",
            "crowd_tolerance": "high",
            "safety_requirement": "medium",
            "typical_duration_hours": 2.5,
            "best_time": "morning"
        },
        {
            "name": "Ancient Monastic Ruins Cycling Tour",
            "categories": ["heritage", "history", "photography"],
            "weather_sensitivity": "high",
            "rain_tolerance": "low",
            "crowd_tolerance": "high",
            "safety_requirement": "medium",
            "typical_duration_hours": 3.5,
            "best_time": "morning"
        }
    ],

    "Polonnaruwa": [
        {
            "name": "Polonnaruwa Ancient Kingdom Bike Tour",
            "categories": ["heritage", "history", "cultural"],
            "weather_sensitivity": "high",
            "rain_tolerance": "low",
            "crowd_tolerance": "high",
            "safety_requirement": "medium",
            "typical_duration_hours": 3,
            "best_time": "morning"
        },
        {
            "name": "Gal Vihara Rock Temple Sculptures",
            "categories": ["heritage", "cultural"],
            "weather_sensitivity": "medium",
            "rain_tolerance": "medium",
            "crowd_tolerance": "high",
            "safety_requirement": "low",
            "typical_duration_hours": 1.5,
            "best_time": "morning"
        }
    ],

    "Jaffna": [
        {
            "name": "Nallur Kandaswamy Kovil Visit",
            "categories": ["cultural", "heritage", "temple"],
            "weather_sensitivity": "low",
            "rain_tolerance": "high",
            "crowd_tolerance": "medium",
            "safety_requirement": "medium",
            "typical_duration_hours": 2,
            "best_time": "morning"
        },
        {
            "name": "Jaffna Dutch Fort Exploration",
            "categories": ["heritage", "history", "photography"],
            "weather_sensitivity": "medium",
            "rain_tolerance": "medium",
            "crowd_tolerance": "high",
            "safety_requirement": "medium",
            "typical_duration_hours": 2,
            "best_time": "evening"
        }
    ],

    "Trincomalee": [
        {
            "name": "Nilaveli Beach & Pigeon Island Snorkeling",
            "categories": ["beach", "wildlife", "adventure"],
            "weather_sensitivity": "high",
            "rain_tolerance": "low",
            "crowd_tolerance": "medium",
            "safety_requirement": "high",
            "typical_duration_hours": 4,
            "best_time": "morning"
        },
        {
            "name": "Koneswaram Hindu Temple Cliffside Visit",
            "categories": ["cultural", "heritage", "photography"],
            "weather_sensitivity": "medium",
            "rain_tolerance": "medium",
            "crowd_tolerance": "high",
            "safety_requirement": "medium",
            "typical_duration_hours": 2,
            "best_time": "morning"
        }
    ],

    "Yala": [
        {
            "name": "Yala National Park Game Safari",
            "categories": ["wildlife", "nature", "adventure", "photography"],
            "weather_sensitivity": "high",
            "rain_tolerance": "low",
            "crowd_tolerance": "medium",
            "safety_requirement": "high",
            "typical_duration_hours": 4,
            "best_time": "early_morning"
        }
    ],

    "Hikkaduwa": [
        {
            "name": "Hikkaduwa Coral Sanctuary Snorkeling",
            "categories": ["beach", "wildlife", "adventure"],
            "weather_sensitivity": "high",
            "rain_tolerance": "low",
            "crowd_tolerance": "medium",
            "safety_requirement": "high",
            "typical_duration_hours": 2.5,
            "best_time": "morning"
        }
    ],

    "Dambulla": [
        {
            "name": "Dambulla Golden Cave Temple Tour",
            "categories": ["heritage", "cultural", "temple"],
            "weather_sensitivity": "low",
            "rain_tolerance": "high",
            "crowd_tolerance": "high",
            "safety_requirement": "medium",
            "typical_duration_hours": 2,
            "best_time": "morning"
        }
    ]
}


def get_destination_activities(destination):
    """Returns benchmark activity list for a destination or fallback general activities."""
    dest = destination.strip().title() if destination else "Nuwara Eliya"
    activities = DESTINATION_ACTIVITIES.get(dest)
    
    if activities:
        return list(activities)
    
    # Fallback general activities for unlisted destination
    return [
        {
            "name": f"{dest} Sightseeing & Heritage Exploration",
            "categories": ["heritage", "cultural", "photography"],
            "weather_sensitivity": "medium",
            "rain_tolerance": "medium",
            "crowd_tolerance": "high",
            "safety_requirement": "medium",
            "typical_duration_hours": 2.5,
            "best_time": "morning"
        },
        {
            "name": f"{dest} Local Dining & Scenic Promenade",
            "categories": ["food", "relaxing"],
            "weather_sensitivity": "low",
            "rain_tolerance": "high",
            "crowd_tolerance": "high",
            "safety_requirement": "low",
            "typical_duration_hours": 1.5,
            "best_time": "evening"
        }
    ]


def match_activity_preferences(activity, user_preferences):
    """Calculates preference match score (0-100) for an activity based on category overlap."""
    if not user_preferences:
        return 85.0
    
    act_cats = activity.get("categories", [])
    matches = [p for p in user_preferences if p in act_cats]
    
    if not matches:
        return 35.0
    
    ratio = len(matches) / len(user_preferences)
    return min(100.0, max(40.0, round(ratio * 100.0)))


def evaluate_activity_weather(activity, weather_suitability_score, rainfall_mm):
    """Evaluates weather suitability for an activity and adds warnings if rainfall exceeds tolerance."""
    score = float(weather_suitability_score)
    rain = float(rainfall_mm)
    rain_tol = activity.get("rain_tolerance", "medium")
    warnings = []

    if rain_tol == "low" and rain > 5.0:
        score -= 25.0
        warnings.append("Outdoor activity may be affected by heavy rainfall.")
    elif rain_tol == "medium" and rain > 10.0:
        score -= 15.0
        warnings.append("Moderate rainfall may reduce outdoor activity comfort.")

    return min(100.0, max(0.0, score)), warnings


def evaluate_activity_crowd(activity, crowd_score, crowd_level):
    """Evaluates crowd suitability for an activity and adds warnings if crowd level exceeds tolerance."""
    score = float(crowd_score)
    crowd_tol = activity.get("crowd_tolerance", "medium")
    warnings = []

    if crowd_tol == "low" and crowd_level in ("High", "Very High"):
        score -= 20.0
        warnings.append("High crowd levels may reduce the experience.")

    return min(100.0, max(0.0, score)), warnings


def evaluate_activity_safety(activity, safety_score, safety_level):
    """Evaluates safety suitability for an activity and adds warnings if safety level is caution."""
    score = float(safety_score)
    safety_req = activity.get("safety_requirement", "medium")
    warnings = []

    if safety_req == "high" and safety_level == "Caution":
        score -= 20.0
        warnings.append("Additional safety caution is recommended.")

    return min(100.0, max(0.0, score)), warnings


def calculate_activity_score(pref_score, weather_score, crowd_score, safety_score, access_score=85.0):
    """
    Calculates composite activity score (0-100) with strongest weight on preference matching.
    """
    weighted = (
        (pref_score * 0.35) +
        (weather_score * 0.25) +
        (crowd_score * 0.15) +
        (safety_score * 0.15) +
        (access_score * 0.10)
    )
    return int(round(min(100.0, max(0.0, weighted))))


def rank_activities(destination, user_preferences, weather_suitability, travel_transport, crowd_safety):
    """
    Ranks destination activities by composite score and returns formatted recommendations.
    """
    raw_activities = get_destination_activities(destination)

    w_score = weather_suitability.get("score", 85)
    rain_mm = weather_suitability.get("rainfall_mm", 2.0)

    c_score = crowd_safety.get("crowd_score", 85)
    c_level = crowd_safety.get("crowd_level", "Low")

    s_score = crowd_safety.get("safety_score", 85)
    s_level = crowd_safety.get("safety_level", "Safe")

    access_score = travel_transport.get("transport_score", 85)

    ranked_items = []

    for act in raw_activities:
        p_score = match_activity_preferences(act, user_preferences)
        act_w_score, w_warns = evaluate_activity_weather(act, w_score, rain_mm)
        act_c_score, c_warns = evaluate_activity_crowd(act, c_score, c_level)
        act_s_score, s_warns = evaluate_activity_safety(act, s_score, s_level)

        final_act_score = calculate_activity_score(p_score, act_w_score, act_c_score, act_s_score, access_score)

        all_warns = w_warns + c_warns + s_warns
        recommended_flag = final_act_score >= 60 and len(all_warns) == 0

        reasons = []
        act_cats = act.get("categories", [])
        
        # Reasons derived from matching logic
        matched = [p for p in user_preferences if p in act_cats]
        if matched:
            reasons.append(f"Strong match for your {matched[0]} preference")
        elif p_score >= 80:
            reasons.append("Great activity choice for this destination")

        if act_w_score >= 75:
            reasons.append("Suitable weather conditions for this activity")

        if act_c_score >= 75:
            reasons.append("Expected crowd levels are manageable")

        if act_s_score >= 75:
            reasons.append("Good safety conditions")

        if not reasons:
            reasons.append("Popular research benchmark destination activity")

        ranked_items.append({
            "name": act["name"],
            "score": final_act_score,
            "categories": act_cats,
            "duration_hours": act.get("typical_duration_hours", 2),
            "best_time": act.get("best_time", "anytime"),
            "recommended": recommended_flag,
            "reasons": reasons,
            "warnings": all_warns
        })

    ranked_items.sort(key=lambda x: x["score"], reverse=True)
    top_activity = ranked_items[0] if ranked_items else None

    return top_activity, ranked_items


def build_activity_recommendations(destination, user_preferences, weather_suitability, travel_transport, crowd_safety):
    """
    Builds the complete activity_recommendations summary object for a destination recommendation.
    """
    top_act, all_acts = rank_activities(
        destination, user_preferences, weather_suitability, travel_transport, crowd_safety
    )

    top_summary = None
    if top_act:
        top_summary = {
            "name": top_act["name"],
            "score": top_act["score"],
            "category": top_act["categories"][0] if top_act["categories"] else "general",
            "duration_hours": top_act["duration_hours"],
            "recommended": top_act["recommended"]
        }

    return {
        "top_activity": top_summary,
        "activities": all_acts,
        "data_source": "Research Benchmark Estimate"
    }
