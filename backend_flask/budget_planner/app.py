from flask import Flask, Blueprint, request, jsonify
from pathlib import Path
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR.parent / ".env")

bp = Blueprint("budget_planner", __name__)

# route generator moved to configurations.py
try:
    from .configurations import generate_route
    from .ai_estimator import get_ai_estimate
    from .route_calculator import calculate_route_distance
    from .fuel_calculator import calculate_route_fuel_cost
    from .hotel_calculator import calculate_route_hotel_cost
    from .food_calculator import calculate_route_food_cost
    from .attraction_calculator import calculate_route_attraction_cost
    from .unified_cost_calculator import build_cost_summary, build_budget_analysis
    from .budget_optimizer import optimize_budget
    from .public_transport_calculator import calculate_public_transport_route_cost, compare_transport_costs
    from .dynamic_route_optimizer import optimize_itinerary
    from .travel_schedule_optimizer import optimize_travel_schedule
    from .personalized_trip_recommender import generate_personalized_recommendation
    from .end_to_end_validator import normalize_trip_input, validate_trip_input, run_end_to_end_validation
    from .data_confidence_engine import load_data_source_metadata, calculate_component_confidence, calculate_overall_confidence, build_confidence_summary
    from .real_time_data_engine import fetch_fuel_prices, fetch_hotel_prices, fetch_public_transport_fares, fetch_attraction_information, fetch_route_information, build_real_time_data_summary
    from .final_system_validator import run_final_system_validation
except ImportError:  # running as a script
    from configurations import generate_route
    from ai_estimator import get_ai_estimate
    from route_calculator import calculate_route_distance
    from fuel_calculator import calculate_route_fuel_cost
    from hotel_calculator import calculate_route_hotel_cost
    from food_calculator import calculate_route_food_cost
    from attraction_calculator import calculate_route_attraction_cost
    from unified_cost_calculator import build_cost_summary, build_budget_analysis
    from budget_optimizer import optimize_budget
    from public_transport_calculator import calculate_public_transport_route_cost, compare_transport_costs
    from dynamic_route_optimizer import optimize_itinerary
    from travel_schedule_optimizer import optimize_travel_schedule
    from personalized_trip_recommender import generate_personalized_recommendation
    from end_to_end_validator import normalize_trip_input, validate_trip_input, run_end_to_end_validation
    from data_confidence_engine import load_data_source_metadata, calculate_component_confidence, calculate_overall_confidence, build_confidence_summary
    from real_time_data_engine import fetch_fuel_prices, fetch_hotel_prices, fetch_public_transport_fares, fetch_attraction_information, fetch_route_information, build_real_time_data_summary
    from final_system_validator import run_final_system_validation

# ==========================================
# HOME
# ==========================================

@bp.route("/")
def home():

    return jsonify({

        "message": "Sri Lanka AI Tourism Planner Running"

    })

# ==========================================
# PREDICT API
# ==========================================

@bp.route("/predict", methods=["POST"])
def predict():

    try:

        # ==========================================
        # GET & NORMALIZE INPUT
        # ==========================================

        raw_data = request.get_json() or {}

        if not raw_data:
            return jsonify({
                "success": False,
                "error": "Missing or invalid JSON request payload"
            }), 400

        data = normalize_trip_input(raw_data)
        is_valid_input, input_warnings = validate_trip_input(data)

        if not is_valid_input:
            return jsonify({
                "success": False,
                "error": f"Invalid trip input payload: {'; '.join(input_warnings)}"
            }), 400

        budget = data["budget"]
        days = data["days"]
        interest = data["interest"]
        travel_type = data["travel_type"]
        transport_mode = data["transport_mode"]
        travelers = data["travelers"]
        adult_travelers = data["adult_travelers"]
        child_travelers = data["child_travelers"]

        fare_class = raw_data.get("fare_class")
        custom_efficiency = raw_data.get("vehicle_efficiency_km_per_liter")
        hotel_tier = raw_data.get("hotel_tier")
        food_tier = raw_data.get("food_tier", "standard")
        include_snacks = bool(raw_data.get("include_snacks", False))
        food_preferences = raw_data.get("food_preferences")

        # ==========================================
        # GENERATE ROUTE
        # ==========================================

        predicted_route = generate_route(

            interest,
            days,
            budget
        )

        # ==========================================
        # CALCULATE ROUTE DISTANCE
        # ==========================================

        route_dist_res = calculate_route_distance(predicted_route)

        if not route_dist_res.get("success", True):
            return jsonify({
                "success": False,
                "error": route_dist_res.get("error", "Distance calculation failed")
            }), 400

        route_distance_data = {
            "total_distance_km": route_dist_res["total_distance_km"],
            "legs": route_dist_res["legs"]
        }

        # ==========================================
        # CALCULATE FUEL COST
        # ==========================================

        fuel_res = calculate_route_fuel_cost(
            total_distance_km=route_dist_res["total_distance_km"],
            transport_mode=transport_mode,
            custom_efficiency=custom_efficiency
        )

        if not fuel_res.get("success", True):
            return jsonify({
                "success": False,
                "error": fuel_res.get("error", "Fuel calculation failed")
            }), 400

        fuel_cost_data = {k: v for k, v in fuel_res.items() if k != "success"}

        # ==========================================
        # CALCULATE PUBLIC TRANSPORT COST
        # ==========================================

        public_transport_cost_data = None
        mode_clean = transport_mode.strip().lower()

        if mode_clean in ("bus", "train", "public transport", "public_transport") or fare_class:
            pt_mode = "bus" if mode_clean == "bus" else "train"
            pt_res = calculate_public_transport_route_cost(
                route=predicted_route,
                transport_mode=pt_mode,
                fare_class=fare_class,
                adult_travelers=adult_travelers,
                child_travelers=child_travelers,
                travelers=travelers
            )
            if pt_res.get("success"):
                public_transport_cost_data = {k: v for k, v in pt_res.items() if k != "success"}

        # ==========================================
        # TRANSPORT COST COMPARISON
        # ==========================================

        transport_comparison_data = compare_transport_costs(
            route=predicted_route,
            total_distance_km=route_distance_data["total_distance_km"],
            selected_mode=transport_mode,
            travelers=travelers,
            adult_travelers=adult_travelers,
            child_travelers=child_travelers,
            custom_efficiency=custom_efficiency
        )

        # ==========================================
        # CALCULATE HOTEL COST
        # ==========================================

        hotel_res = calculate_route_hotel_cost(
            route=predicted_route,
            days=days,
            travelers=travelers,
            hotel_tier=hotel_tier,
            user_budget=budget
        )

        if not hotel_res.get("success", True):
            return jsonify({
                "success": False,
                "error": hotel_res.get("error", "Hotel cost calculation failed")
            }), 400

        hotel_cost_data = {k: v for k, v in hotel_res.items() if k != "success"}

        # ==========================================
        # CALCULATE FOOD COST
        # ==========================================

        food_res = calculate_route_food_cost(
            route=predicted_route,
            days=days,
            travelers=travelers,
            food_tier=food_tier,
            include_snacks=include_snacks,
            food_preferences=food_preferences,
            user_budget=budget
        )

        if not food_res.get("success", True):
            return jsonify({
                "success": False,
                "error": food_res.get("error", "Food cost calculation failed")
            }), 400

        food_cost_data = {k: v for k, v in food_res.items() if k != "success"}

        # ==========================================
        # CALCULATE ATTRACTION COST
        # ==========================================

        attraction_res = calculate_route_attraction_cost(
            route=predicted_route,
            days=days,
            travelers=travelers,
            adult_travelers=adult_travelers,
            child_travelers=child_travelers,
            interest=interest,
            user_budget=budget
        )

        if not attraction_res.get("success", True):
            return jsonify({
                "success": False,
                "error": attraction_res.get("error", "Attraction cost calculation failed")
            }), 400

        attraction_cost_data = {k: v for k, v in attraction_res.items() if k != "success"}

        # ==========================================
        # UNIFIED COST CALCULATOR
        # ==========================================

        trip_cost_data = build_cost_summary(
            fuel_data=fuel_cost_data,
            hotel_data=hotel_cost_data,
            food_data=food_cost_data,
            attraction_data=attraction_cost_data,
            user_budget=budget,
            days=days,
            travelers=travelers,
            public_transport_data=public_transport_cost_data
        )

        # ==========================================
        # INTELLIGENT BUDGET OPTIMIZER
        # ==========================================

        budget_opt_data = optimize_budget(
            route=predicted_route,
            days=days,
            travelers=travelers,
            adult_travelers=adult_travelers,
            child_travelers=child_travelers,
            interest=interest,
            travel_type=travel_type,
            transport_mode=transport_mode,
            hotel_tier=hotel_tier,
            food_tier=food_tier,
            include_snacks=include_snacks,
            food_preferences=food_preferences,
            user_budget=budget,
            original_fuel_data=fuel_cost_data,
            original_hotel_data=hotel_cost_data,
            original_food_data=food_cost_data,
            original_attraction_data=attraction_cost_data,
            original_summary=trip_cost_data
        )

        # ==========================================
        # DYNAMIC ROUTE OPTIMIZER
        # ==========================================

        route_opt_data = optimize_itinerary(
            route=predicted_route,
            days=days,
            travelers=travelers,
            adult_travelers=adult_travelers,
            child_travelers=child_travelers,
            interest=interest,
            travel_type=travel_type,
            transport_mode=transport_mode,
            hotel_tier=hotel_tier,
            food_tier=food_tier,
            include_snacks=include_snacks,
            food_preferences=food_preferences,
            user_budget=budget,
            original_summary=trip_cost_data
        )

        # ==========================================
        # CONTEXT-AWARE TRAVEL SCHEDULE OPTIMIZER
        # ==========================================

        target_opt_route = route_opt_data.get("optimized_route", predicted_route)
        travel_sched_data = optimize_travel_schedule(
            route=target_opt_route,
            days=days,
            travelers=travelers,
            adult_travelers=adult_travelers,
            child_travelers=child_travelers,
            interest=interest,
            travel_type=travel_type,
            transport_mode=transport_mode,
            hotel_tier=hotel_tier,
            food_tier=food_tier,
            include_snacks=include_snacks,
            food_preferences=food_preferences,
            user_budget=budget,
            original_summary=trip_cost_data
        )

        # ==========================================
        # PERSONALIZED MULTI-OBJECTIVE RECOMMENDATION (STEP 11)
        # ==========================================

        personalized_rec_data, research_metrics_data, best_trip = generate_personalized_recommendation(
            predicted_route=predicted_route,
            budget=budget,
            days=days,
            travelers=travelers,
            adult_travelers=adult_travelers,
            child_travelers=child_travelers,
            interest=interest,
            travel_type=travel_type,
            transport_mode=transport_mode,
            hotel_tier=hotel_tier,
            food_tier=food_tier
        )

        final_selected_route = best_trip["route"]
        final_trip_cost = best_trip["summary"]
        final_travel_schedule = best_trip["travel_schedule"]

        # Ensure route_optimization and research_metrics reflect final selected route
        route_opt_data["optimized_route"] = final_selected_route
        route_opt_data["optimized_cost_lkr"] = best_trip["total_cost_lkr"]
        research_metrics_data["initial_route"] = predicted_route
        research_metrics_data["optimized_route"] = final_selected_route
        research_metrics_data["final_selected_route"] = final_selected_route

        # ==========================================
        # DATA FRESHNESS & CONFIDENCE ENGINE (STEP 13)
        # ==========================================

        is_pt_used = transport_mode.strip().lower() in ("bus", "train", "public transport", "public_transport")
        meta_map = load_data_source_metadata()

        comp_confidences = {}
        active_comps = ["route", "fuel", "hotel", "food", "attractions", "schedule", "recommendation"]
        if is_pt_used:
            active_comps.append("public_transport")

        for c in active_comps:
            c_meta = meta_map.get(c, {
                "source_type": "research_benchmark",
                "source_name": "Research Benchmark Estimate",
                "last_updated": "2026-08-01",
                "refresh_interval_days": 30,
                "reliability_score": 75.0
            })
            comp_confidences[c] = calculate_component_confidence(c, c_meta)

        overall_conf = calculate_overall_confidence(comp_confidences, is_public_transport_used=is_pt_used)
        data_confidence_data = build_confidence_summary(comp_confidences, overall_conf)
        data_confidence_data["components"] = comp_confidences

        # Extend research_metrics for research transparency
        research_metrics_data["overall_data_confidence_score"] = data_confidence_data["overall_confidence_score"]
        research_metrics_data["data_confidence_level"] = data_confidence_data["confidence_level"]
        research_metrics_data["lowest_confidence_component"] = data_confidence_data["lowest_confidence_component"]
        research_metrics_data["stale_data_components"] = data_confidence_data["stale_data_components"]
        research_metrics_data["benchmark_data_components"] = data_confidence_data["benchmark_data_components"]

        # ==========================================
        # REAL-TIME DATA INTEGRATION ENGINE (STEP 14)
        # ==========================================

        real_time_component_statuses = {
            "fuel": fetch_fuel_prices({"transport_mode": transport_mode}),
            "hotel": fetch_hotel_prices("Kandy", hotel_tier),
            "food": {"component": "food", "status": "benchmark", "source": "Research Benchmark Estimate", "source_type": "research_benchmark"},
            "attractions": fetch_attraction_information("Temple of the Tooth"),
            "transport": fetch_public_transport_fares("Colombo", "Kandy", transport_mode),
            "route": fetch_route_information("Colombo", "Kandy"),
            "schedule": {"component": "schedule", "status": "benchmark", "source": "Research Benchmark Estimate", "source_type": "research_benchmark"}
        }

        real_time_data = build_real_time_data_summary(real_time_component_statuses)

        # Extend research_metrics for Step 14 real-time evaluation
        research_metrics_data["real_time_data_status"] = real_time_data["status"]
        research_metrics_data["live_components_count"] = len(real_time_data["live_components"])
        research_metrics_data["cached_components_count"] = len(real_time_data["cached_components"])
        research_metrics_data["benchmark_components_count"] = len(real_time_data["benchmark_components"])
        research_metrics_data["failed_components_count"] = len(real_time_data["failed_components"])
        research_metrics_data["data_refresh_timestamp"] = real_time_data["last_refresh"]
        research_metrics_data["live_data_used"] = len(real_time_data["live_components"]) > 0

        # ==========================================
        # ASK CHATGPT FOR COST BREAKDOWN + HOTELS (WITH FALLBACK)
        # ==========================================

        try:
            ai_estimate = get_ai_estimate(
                final_selected_route,
                budget,
                days,
                interest,
                travel_type,
                transport_mode,
                calculated_hotel_cost_data=hotel_cost_data,
                calculated_food_cost_data=food_cost_data,
                calculated_attraction_cost_data=attraction_cost_data,
                unified_cost_summary=final_trip_cost,
                budget_optimization_data=budget_opt_data,
                public_transport_cost_data=public_transport_cost_data,
                transport_comparison_data=transport_comparison_data,
                route_optimization_data=route_opt_data,
                travel_schedule_data=final_travel_schedule,
                personalized_recommendation_data=personalized_rec_data,
                research_metrics_data=research_metrics_data,
                data_confidence_data=data_confidence_data,
                real_time_data=real_time_data
            )
        except Exception as ai_err:
            ai_estimate = {
                "minimum_recommended_budget_lkr": final_trip_cost["total_trip_cost_lkr"],
                "recommended_hotels": []
            }

        ml_predicted_budget = ai_estimate.get("minimum_recommended_budget_lkr", budget)
        research_metrics_data["ml_predicted_budget_lkr"] = ml_predicted_budget
        real_cost_val = float(final_trip_cost["total_trip_cost_lkr"])
        research_metrics_data["real_calculated_cost_lkr"] = real_cost_val
        research_metrics_data["prediction_difference_lkr"] = round(ml_predicted_budget - real_cost_val, 2)
        research_metrics_data["prediction_error_percentage"] = 0.0 if real_cost_val == 0 else round((abs(ml_predicted_budget - real_cost_val) / real_cost_val) * 100, 2)

        # ==========================================
        # RESEARCH BUDGET ANALYSIS
        # ==========================================

        budget_analysis_data = build_budget_analysis(
            ml_predicted_budget=ml_predicted_budget,
            real_calculated_cost=real_cost_val
        )

        # ==========================================
        # FINAL RESPONSE
        # ==========================================

        is_budget_sufficient = (real_cost_val <= budget)
        minimum_budget = ai_estimate.get("minimum_recommended_budget_lkr", real_cost_val)

        message = None
        if not is_budget_sufficient:
            message = (
                f"Your budget of {budget} LKR is insufficient for this "
                f"{days}-day trip ({final_selected_route}). Real calculated trip cost is "
                f"{real_cost_val} LKR (Deficit: {final_trip_cost['budget_deficit_lkr']} LKR)."
            )

        # ==========================================
        # END-TO-END VALIDATION (STEP 12)
        # ==========================================

        validation_data = run_end_to_end_validation(
            input_data=data,
            final_selected_route=final_selected_route,
            final_trip_cost=final_trip_cost,
            final_schedule=final_travel_schedule,
            recommendation_data=personalized_rec_data
        )

        effective_fuel_cost = final_trip_cost["cost_breakdown"]["fuel_lkr"]
        calculated_hotel_total = final_trip_cost["cost_breakdown"]["hotel_lkr"]
        calculated_food_total = final_trip_cost["cost_breakdown"]["food_lkr"]
        calculated_attraction_total = final_trip_cost["cost_breakdown"]["attractions_lkr"]

        prediction = {

            "predicted_route": final_selected_route,

            "route_distance": route_distance_data,

            "fuel_cost": fuel_cost_data,

            "public_transport_cost": public_transport_cost_data,

            "transport_comparison": transport_comparison_data,

            "hotel_cost": hotel_cost_data,

            "food_cost": food_cost_data,

            "attraction_cost": attraction_cost_data,

            "trip_cost": final_trip_cost,

            "budget_analysis": budget_analysis_data,

            "budget_optimization": budget_opt_data,

            "route_optimization": route_opt_data,

            "travel_schedule": final_travel_schedule,

            "personalized_recommendation": personalized_rec_data,

            "research_metrics": research_metrics_data,

            "validation": validation_data,

            "data_confidence": data_confidence_data,

            "real_time_data": real_time_data,

            "calculated_fuel_cost_lkr": effective_fuel_cost,

            "calculated_hotel_cost_lkr": calculated_hotel_total,

            "calculated_food_cost_lkr": calculated_food_total,

            "calculated_attraction_cost_lkr": calculated_attraction_total,

            "estimated_total_budget_lkr": ai_estimate.get("estimated_total_budget_lkr", real_cost_val),

            "estimated_daily_budget_lkr": ai_estimate.get("estimated_daily_budget_lkr", round(real_cost_val / days, 2)),

            "estimated_hotel_cost_lkr": ai_estimate.get("estimated_hotel_cost_lkr", calculated_hotel_total),

            "estimated_fuel_cost_lkr": ai_estimate.get("estimated_fuel_cost_lkr", effective_fuel_cost),

            "estimated_food_cost_lkr": ai_estimate.get("estimated_food_cost_lkr", calculated_food_total),

            "estimated_attraction_cost_lkr": ai_estimate.get("estimated_attraction_cost_lkr", calculated_attraction_total),

            "minimum_recommended_budget_lkr": minimum_budget,

            "recommended_hotels": ai_estimate.get("recommended_hotels", []),

            "is_budget_sufficient": is_budget_sufficient,

            "message": message
        }

        # ==========================================
        # FINAL SYSTEM VALIDATION (STEP 15)
        # ==========================================

        final_system_validation_data = run_final_system_validation(
            input_data=data,
            prediction_payload=prediction
        )

        prediction["final_system_validation"] = final_system_validation_data
        research_metrics_data["final_system_validation_passed"] = final_system_validation_data["valid"]

        response = {

            "success": True,

            "input": {

                "budget": budget,

                "days": days,

                "interest": interest,

                "travel_type": travel_type,

                "transport_mode": transport_mode
            },

            "prediction": prediction
        }

        return jsonify(response)

    except KeyError as ke:
        return jsonify({
            "success": False,
            "error": f"Missing required field: {str(ke)}"
        }), 400

    except Exception as e:

        return jsonify({

            "success": False,

            "error": str(e)
        }), 500

# ==========================================
# RUN APP
# ==========================================

if __name__ == "__main__":

    app = Flask(__name__)
    app.register_blueprint(bp)
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )