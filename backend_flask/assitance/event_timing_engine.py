"""
Event Timing & Daily Activity Scheduling Engine for Component 2 — Step 6.
Calculates optimal time windows, travel arrival feasibility, non-overlapping daily schedules, and timing suitability.
"""

TIME_PERIODS = {
    "early_morning": {"label": "Early Morning", "range": "06:00-09:00", "start_hour": 6.0, "end_hour": 9.0},
    "morning": {"label": "Morning", "range": "09:00-12:00", "start_hour": 9.0, "end_hour": 12.0},
    "midday": {"label": "Midday", "range": "12:00-15:00", "start_hour": 12.0, "end_hour": 15.0},
    "afternoon": {"label": "Afternoon", "range": "15:00-18:00", "start_hour": 15.0, "end_hour": 18.0},
    "evening": {"label": "Evening", "range": "18:00-21:00", "start_hour": 18.0, "end_hour": 21.0}
}


def get_time_periods():
    """Returns standardized time period definitions."""
    return TIME_PERIODS


def evaluate_activity_timing(activity, time_period_key):
    """
    Evaluates match score (0-100) between an activity's preferred best_time and a candidate time_period.
    """
    best_time = activity.get("best_time", "anytime") if isinstance(activity, dict) else "anytime"
    
    if best_time == "anytime":
        return 85.0
    
    if best_time == time_period_key:
        return 100.0
    
    # Check adjacent time periods
    period_order = ["early_morning", "morning", "midday", "afternoon", "evening"]
    if best_time in period_order and time_period_key in period_order:
        diff = abs(period_order.index(best_time) - period_order.index(time_period_key))
        if diff == 1:
            return 75.0
        elif diff == 2:
            return 55.0

    return 40.0


def calculate_timing_score(best_time_match, weather_timing_score=85.0, crowd_timing_score=85.0, safety_timing_score=85.0, feasibility_score=85.0):
    """
    Calculates deterministic timing score (0-100) with strongest weight on preferred best_time match.
    """
    weighted = (
        (best_time_match * 0.35) +
        (weather_timing_score * 0.25) +
        (crowd_timing_score * 0.20) +
        (safety_timing_score * 0.10) +
        (feasibility_score * 0.10)
    )
    return int(round(min(100.0, max(0.0, weighted))))


def check_activity_time_feasibility(start_hour, duration_hours, arrival_hour=6.0):
    """
    Checks if an activity start time and duration are realistically feasible given arrival time and daily bounds.
    """
    start = float(start_hour)
    dur = float(duration_hours)
    arr = float(arrival_hour)

    if start < arr:
        return False, "Travel time makes the preferred activity window impractical."
    
    if (start + dur) > 21.0:
        return False, "Activity duration exceeds reasonable daily operating hours."

    return True, "Activity fits within realistic daily schedule."


def generate_activity_time_window(start_hour, duration_hours):
    """
    Formats numeric start hour and duration into string time window 'HH:MM-HH:MM' (e.g. 6.5, 4.0 -> '06:30-10:30').
    """
    s_h = int(start_hour)
    s_m = int(round((start_hour - s_h) * 60))
    if s_m >= 60:
        s_h += 1
        s_m = 0

    end_total = start_hour + duration_hours
    e_h = int(end_total)
    e_m = int(round((end_total - e_h) * 60))
    if e_m >= 60:
        e_h += 1
        e_m = 0

    return f"{s_h:02d}:{s_m:02d}-{e_h:02d}:{e_m:02d}"


def get_period_key_from_hour(hour):
    """Maps start hour float to period key."""
    h = float(hour)
    if h < 9.0:
        return "early_morning"
    elif h < 12.0:
        return "morning"
    elif h < 15.0:
        return "midday"
    elif h < 18.0:
        return "afternoon"
    else:
        return "evening"


def build_event_timing_summary(destination, activities, travel_transport, weather_suitability, crowd_safety):
    """
    Builds non-overlapping daily activity schedule and event timing summary for a destination.
    """
    travel_time_hours = float(travel_transport.get("estimated_travel_time_hours", 2.5))
    origin = travel_transport.get("origin", "Colombo")

    # Determine practical arrival hour: if at destination or local, day starts early (6.0)
    if origin == destination or travel_time_hours <= 0:
        arrival_hour = 6.0
    elif travel_time_hours <= 1.5:
        arrival_hour = 7.5
    else:
        arrival_hour = min(14.0, 7.0 + travel_time_hours)

    w_score = float(weather_suitability.get("score", 85))
    c_score = float(crowd_safety.get("crowd_score", 85))
    c_level = crowd_safety.get("crowd_level", "Low")
    s_score = float(crowd_safety.get("safety_score", 85))

    # Extract activities list
    acts_list = []
    if isinstance(activities, dict):
        acts_list = activities.get("activities", [])
    elif isinstance(activities, list):
        acts_list = activities

    daily_schedule = []
    current_time_pointer = max(6.5, arrival_hour)
    overall_feasible = True

    for idx, act in enumerate(acts_list[:3]):
        dur = float(act.get("duration_hours", 2.0))
        pref_best_time = act.get("best_time", "anytime")

        # Determine start hour based on preferred time or current pointer
        if pref_best_time == "early_morning" and arrival_hour <= 7.0:
            start_h = max(current_time_pointer, 6.5)
        elif pref_best_time == "morning" and arrival_hour <= 10.0:
            start_h = max(current_time_pointer, 9.0)
        elif pref_best_time == "afternoon" and arrival_hour <= 15.0:
            start_h = max(current_time_pointer, 15.0)
        elif pref_best_time == "evening" and arrival_hour <= 18.0:
            start_h = max(current_time_pointer, 18.0)
        else:
            start_h = current_time_pointer

        # Check feasibility
        is_feasible, feas_reason = check_activity_time_feasibility(start_h, dur, arrival_hour)
        if not is_feasible:
            overall_feasible = False

        period_key = get_period_key_from_hour(start_h)
        time_match_score = evaluate_activity_timing(act, period_key)

        # Timing adjustments
        c_timing_score = c_score
        if c_level in ("High", "Very High") and period_key == "early_morning":
            c_timing_score += 10.0  # Early morning helps avoid high crowd
        elif c_level in ("High", "Very High") and period_key == "midday":
            c_timing_score -= 15.0

        feas_score_val = 90.0 if is_feasible else 40.0

        final_t_score = calculate_timing_score(
            time_match_score, w_score, c_timing_score, s_score, feas_score_val
        )

        time_window_str = generate_activity_time_window(start_h, dur)

        reasons = []
        warnings = []

        if time_match_score >= 90:
            reasons.append(f"Matches the preferred {TIME_PERIODS.get(period_key, {}).get('label', period_key).lower()} period")
        
        if w_score >= 80:
            reasons.append("Suitable weather conditions for this activity window")

        if period_key == "early_morning":
            reasons.append("Early timing helps avoid higher crowd pressure")

        if not is_feasible:
            warnings.append(feas_reason)

        daily_schedule.append({
            "activity": act.get("name", f"Activity {idx+1}"),
            "time": time_window_str,
            "duration_hours": dur,
            "timing_score": final_t_score,
            "feasible": is_feasible,
            "reasons": reasons,
            "warnings": warnings
        })

        # Advance pointer for next activity with 30-min (0.5h) rest buffer
        current_time_pointer = start_h + dur + 0.5

    top_sched = daily_schedule[0] if daily_schedule else {
        "activity": "Destination Sightseeing",
        "time": "08:00-11:00",
        "duration_hours": 3,
        "timing_score": 88,
        "feasible": True,
        "reasons": ["Standard morning timing window"],
        "warnings": []
    }

    best_period_key = get_period_key_from_hour(6.5 if top_sched["time"].startswith("06") else 9.0)

    return {
        "best_activity_time": top_sched["time"],
        "best_time_period": best_period_key,
        "timing_score": top_sched["timing_score"],
        "daily_schedule": daily_schedule,
        "schedule_feasible": overall_feasible,
        "data_source": "Research Benchmark Estimate"
    }
