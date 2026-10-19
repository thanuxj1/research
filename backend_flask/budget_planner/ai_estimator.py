import json
import os

from openai import OpenAI

_client = None


def _get_client():

    global _client

    if _client is None:

        api_key = os.environ.get("OPENAI_API_KEY")

        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY environment variable is not set"
            )

        _client = OpenAI(api_key=api_key)

    return _client


def _stops(route):

    return [
        p.strip()
        for p in route.split("->")
        if p.strip() != "Colombo"
    ]


def get_ai_estimate(
    predicted_route,
    budget,
    days,
    interest,
    travel_type,
    transport_mode,
    model=None,
    calculated_hotel_cost_data=None,
    calculated_food_cost_data=None,
    calculated_attraction_cost_data=None,
    unified_cost_summary=None,
    budget_optimization_data=None,
    public_transport_cost_data=None,
    transport_comparison_data=None,
    route_optimization_data=None,
    travel_schedule_data=None,
    personalized_recommendation_data=None,
    research_metrics_data=None,
    data_confidence_data=None,
    real_time_data=None,
):
    """Ask ChatGPT for a cost breakdown and recommendations for a route.

    Incorporates dataset-driven hotel, food, attraction, unified trip cost, optimization, public transport, route optimization, travel schedule, personalized recommendation, data confidence, and real-time data totals when provided.

    Returns a dict with the estimated_* cost keys and recommended_hotels.
    """

    client = _get_client()
    model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    stops = _stops(predicted_route)

    context_lines = []
    preset_recommended_hotels = []

    if calculated_hotel_cost_data and calculated_hotel_cost_data.get("stays"):
        calc_hotel_total = calculated_hotel_cost_data.get("total_cost_lkr", 0)
        context_lines.append(f"- Calculated Hotel Accommodation Cost (from dataset): {calc_hotel_total} LKR")

        for stay in calculated_hotel_cost_data["stays"]:
            place = stay.get("destination", "")
            opts = stay.get("options", {})
            for t_key, t_name in [("budget", "budget"), ("mid_range", "mid-range"), ("premium", "premium")]:
                if t_key in opts:
                    opt = opts[t_key]
                    preset_recommended_hotels.append({
                        "hotel_name": opt.get("hotel_name", f"{place} Hotel"),
                        "place": place,
                        "tier": t_name,
                        "price_lkr": opt.get("total_lkr", 0)
                    })

    if calculated_food_cost_data:
        calc_food_total = calculated_food_cost_data.get("total_cost_lkr", 0)
        context_lines.append(f"- Calculated Food Cost (from dataset): {calc_food_total} LKR")

    if calculated_attraction_cost_data:
        calc_attr_total = calculated_attraction_cost_data.get("total_cost_lkr", 0)
        context_lines.append(f"- Calculated Attraction Entry Fee Cost (from dataset): {calc_attr_total} LKR")

    if unified_cost_summary:
        context_lines.append(f"- Unified Calculated Real Trip Cost: {unified_cost_summary.get('total_trip_cost_lkr')} LKR")
        context_lines.append(f"- Calculated Budget Status: {unified_cost_summary.get('budget_status')}")

    if budget_optimization_data:
        context_lines.append(f"- Budget Optimization Status: {budget_optimization_data.get('optimization_status')}")
        context_lines.append(f"- Potential Optimization Savings: {budget_optimization_data.get('savings_lkr')} LKR")

    if public_transport_cost_data:
        context_lines.append(f"- Public Transport Calculated Cost: {public_transport_cost_data.get('total_cost_lkr')} LKR")

    if transport_comparison_data:
        context_lines.append(f"- Transport Comparison Cheapest Mode: {transport_comparison_data.get('cheapest_option')} ({transport_comparison_data.get('cheapest_cost_lkr')} LKR)")

    if route_optimization_data:
        context_lines.append(f"- Route Optimization Best Route: {route_optimization_data.get('optimized_route')}")

    if travel_schedule_data:
        context_lines.append(f"- Travel Schedule Score: {travel_schedule_data.get('schedule_score')}/100")
        if travel_schedule_data.get("schedule_summary"):
            context_lines.append(f"- Schedule Feasibility: {travel_schedule_data['schedule_summary'].get('feasibility', '')}")

    if personalized_recommendation_data and personalized_recommendation_data.get("selected_trip"):
        sel = personalized_recommendation_data["selected_trip"]
        context_lines.append(f"- Final Multi-Objective Recommended Route: {sel.get('route')}")
        context_lines.append(f"- Recommended Transport Mode: {sel.get('transport_mode')}")
        context_lines.append(f"- Recommended Trip Total Cost: {sel.get('total_cost_lkr')} LKR")
        context_lines.append(f"- Overall Decision Engine Score: {personalized_recommendation_data.get('overall_score')}/100")

    if data_confidence_data:
        context_lines.append(f"- Data Provenance Overall Confidence Score: {data_confidence_data.get('overall_confidence_score')}/100 ({data_confidence_data.get('confidence_level')})")
        context_lines.append(f"- Lowest Confidence Data Component: {data_confidence_data.get('lowest_confidence_component')}")

    if real_time_data:
        context_lines.append(f"- Real-Time Data Status: {real_time_data.get('status')}")

    extra_context = ("\n" + "\n".join(context_lines)) if context_lines else ""

    prompt = f"""You are a Sri Lanka travel budget planner.

Trip details:
- Traveler's target budget: {budget} LKR
- Duration: {days} days
- Interest: {interest}
- Travel type: {travel_type}
- Transport mode: {transport_mode}
- Route: {predicted_route}{extra_context}

First, work out "minimum_recommended_budget_lkr": the lowest realistic
total cost (in LKR, real market prices) for a traveler to actually
complete this exact route and duration using the cheapest reasonable
options (budget hotels, public/shared transport where applicable,
basic meals). This number must NOT depend on the traveler's stated
budget — it is the true minimum this trip costs.

Then produce "estimated_total_budget_lkr": your genuine, real-world
cost estimate for this trip at a comfort level matching a traveler
aiming to spend around {budget} LKR. This is a real market-based
estimate, NOT a forced match to {budget} — actual trip costs vary, so
if {budget} is a realistic target for this route/duration, your
estimate should naturally land somewhere close to it (commonly within
about 10% either way, e.g. a traveler targeting 10000 LKR might
realistically end up spending somewhere in the 9000-11000 LKR range),
never suspiciously exact. If {budget} is unrealistically low for this
trip (below minimum_recommended_budget_lkr), ignore it and estimate the
real cost of actually doing this trip instead (it will land at or
above minimum_recommended_budget_lkr).

estimated_hotel_cost_lkr + estimated_fuel_cost_lkr +
estimated_food_cost_lkr + estimated_attraction_cost_lkr must add up to
estimated_total_budget_lkr, and the split between them should reflect
this specific trip (route, transport mode, travel type) rather than a
fixed formula.

For each stop in the route (excluding Colombo): {", ".join(stops)}
recommend exactly 3 hotel options — one budget-tier, one mid-range, and
one premium — with realistic real-world prices, so the traveler can see
their real choices.

Respond with ONLY a JSON object in exactly this shape (numbers only, no
strings, no extra keys):

{{
  "minimum_recommended_budget_lkr": <number>,
  "estimated_total_budget_lkr": <number>,
  "estimated_daily_budget_lkr": <number>,
  "estimated_hotel_cost_lkr": <number>,
  "estimated_fuel_cost_lkr": <number>,
  "estimated_food_cost_lkr": <number>,
  "estimated_attraction_cost_lkr": <number>,
  "recommended_hotels": [
    {{"place": "<stop name>", "hotel_name": "<hotel name>", "tier": "budget", "price_lkr": <number>}},
    {{"place": "<stop name>", "hotel_name": "<hotel name>", "tier": "mid-range", "price_lkr": <number>}},
    {{"place": "<stop name>", "hotel_name": "<hotel name>", "tier": "premium", "price_lkr": <number>}}
  ]
}}

recommended_hotels must contain exactly 3 entries (budget, mid-range,
premium) for every stop listed above — {len(stops) * 3} entries total."""

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a budget planning assistant for Sri Lankan "
                    "tourism. You always reply with strict JSON only."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.4,
    )

    content = completion.choices[0].message.content
    result = json.loads(content)

    required_keys = [
        "estimated_total_budget_lkr",
        "estimated_daily_budget_lkr",
        "estimated_hotel_cost_lkr",
        "estimated_fuel_cost_lkr",
        "estimated_food_cost_lkr",
        "estimated_attraction_cost_lkr",
        "minimum_recommended_budget_lkr",
        "recommended_hotels",
    ]

    missing = [k for k in required_keys if k not in result]

    if missing:
        raise ValueError(
            f"AI response missing keys: {', '.join(missing)}"
        )

    # Use dataset calculated hotel cost if available
    if calculated_hotel_cost_data and calculated_hotel_cost_data.get("total_cost_lkr") is not None:
        result["estimated_hotel_cost_lkr"] = calculated_hotel_cost_data["total_cost_lkr"]

    # Use dataset calculated food cost if available
    if calculated_food_cost_data and calculated_food_cost_data.get("total_cost_lkr") is not None:
        result["estimated_food_cost_lkr"] = calculated_food_cost_data["total_cost_lkr"]

    # Use dataset calculated attraction cost if available
    if calculated_attraction_cost_data and calculated_attraction_cost_data.get("total_cost_lkr") is not None:
        result["estimated_attraction_cost_lkr"] = calculated_attraction_cost_data["total_cost_lkr"]

    # Use preset dataset hotel options if available and matching stop count
    if preset_recommended_hotels and len(preset_recommended_hotels) == len(stops) * 3:
        result["recommended_hotels"] = preset_recommended_hotels

    if unified_cost_summary and unified_cost_summary.get("total_trip_cost_lkr") is not None:
        total_calc = unified_cost_summary["total_trip_cost_lkr"]
        result["estimated_total_budget_lkr"] = total_calc
        result["is_budget_sufficient"] = (total_calc <= budget)
    else:
        # Sufficiency is judged against the true minimum, not the estimate.
        result["is_budget_sufficient"] = (
            budget >= result["minimum_recommended_budget_lkr"]
        )

    return result





