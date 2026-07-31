"""
AI Advisor API Endpoint
IT22629180

Provides personalized safety analysis per user profile, city, and travel month.

Endpoints:
  GET  /advisor/profile-report   — full personalized safety report
  GET  /advisor/patterns         — ML-discovered recurring incident patterns
  GET  /advisor/seasonal-calendar — monthly risk index per city
  GET  /advisor/location-types   — risk breakdown by venue type
  GET  /advisor/city-profile     — detailed city-level safety stats
"""
import os
import json
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List, Dict
from app.db.session import get_db
from app.db.models import Report
from app.ml.pattern_predictor import (
    get_predictor, SAFETY_TIPS, PROFILE_RISK_MAP, PROFILE_MULTIPLIERS
)
from app.ml.review_analyzer import (
    get_analyzer, MONTH_RISK_BOOST, LOCATION_TYPE_BASE_RISK, CITY_COORDS
)

router = APIRouter()

# ── Load cached pattern insights if available ─────────────────────────────────
_INSIGHTS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "ml", "models", "pattern_insights.json"
)

def _load_insights() -> Dict:
    try:
        if os.path.exists(_INSIGHTS_PATH):
            with open(_INSIGHTS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

_cached_insights: Dict = {}


def _get_insights() -> Dict:
    global _cached_insights
    if not _cached_insights:
        _cached_insights = _load_insights()
    return _cached_insights


# ── Month name helper ─────────────────────────────────────────────────────────
_MONTH_NAMES = {
    1:"January",2:"February",3:"March",4:"April",5:"May",6:"June",
    7:"July",8:"August",9:"September",10:"October",11:"November",12:"December"
}

_PROFILE_ICONS = {
    "Solo Female": "👩",
    "Solo Male": "👨",
    "Couple": "💑",
    "Family": "👨‍👩‍👧",
    "Group": "👥",
    "General": "🌍",
}

_SEASON_LABELS = {
    range(5, 10):  {"label": "SW Monsoon Season", "icon": "🌧️", "warning": "Heavy rainfall on west & south coasts. Some attractions may be closed. Roads can flood."},
    range(10, 13): {"label": "NE Monsoon Season", "icon": "🌦️", "warning": "Rainfall on north & east coasts. Best time for west/south coast beaches."},
}

def _get_season_info(month: int) -> Dict:
    for r, info in _SEASON_LABELS.items():
        if month in r:
            return info
    return {"label": "Dry Season", "icon": "☀️", "warning": None}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/profile-report")
def get_profile_report(
    profile: str = Query("General", description="Traveller profile"),
    city: Optional[str] = Query(None, description="Destination city"),
    month: int = Query(6, ge=1, le=12, description="Travel month (1-12)"),
    db: Session = Depends(get_db),
):
    """
    Returns a comprehensive personalized safety report for a user profile.
    Combines ML predictions, seasonal data, location patterns, and custom tips.
    """
    analyzer  = get_analyzer()
    predictor = get_predictor()
    insights  = _get_insights()

    # Normalize profile
    valid_profiles = list(SAFETY_TIPS.keys())
    if profile not in valid_profiles:
        profile = "General"

    # ── 1. Personalised safety tips ───────────────────────────────────────────
    tips = SAFETY_TIPS.get(profile, SAFETY_TIPS["General"])

    # ── 2. Threat risk scores (profile-weighted) ──────────────────────────────
    profile_threats = PROFILE_RISK_MAP.get(profile, PROFILE_RISK_MAP["General"])
    multipliers = PROFILE_MULTIPLIERS.get(profile, {})

    # Pull DB scam counts for the city
    city_scam_counts: Dict[str, int] = {}
    if city:
        rows = (
            db.query(Report.scam_type, func.count(Report.id).label("cnt"))
            .filter(Report.location_name.ilike(f"%{city}%"))
            .filter(Report.scam_type.isnot(None))
            .group_by(Report.scam_type)
            .order_by(func.count(Report.id).desc())
            .limit(10)
            .all()
        )
        city_scam_counts = {r.scam_type: r.cnt for r in rows}

    # Build threat scores combining DB data + profile risk + multipliers
    threat_scores: Dict[str, float] = {}
    total_city = sum(city_scam_counts.values()) or 1
    for scam_type, count in city_scam_counts.items():
        base = count / total_city
        mult = multipliers.get(scam_type, 1.0)
        threat_scores[scam_type] = base * mult

    for scam in profile_threats:
        if scam not in threat_scores:
            threat_scores[scam] = 0.12 * multipliers.get(scam, 1.0)

    top_threats = sorted(threat_scores.items(), key=lambda x: -x[1])[:6]
    threats_list = [
        {
            "scam_type": t,
            "score": round(min(s, 1.0), 3),
            "likelihood_label": "High" if s > 0.5 else ("Moderate" if s > 0.25 else "Low"),
        }
        for t, s in top_threats
    ]

    # ── 3. ML Prediction (if city has coordinates) ────────────────────────────
    ml_prediction = None
    city_profile_data = analyzer.get_city_profile(city) if city else None
    if city_profile_data and city_profile_data.get("lat"):
        lat = city_profile_data["lat"]
        lon = city_profile_data["lon"]
        if not predictor._trained:
            reports = db.query(Report).filter(
                Report.latitude.isnot(None), Report.longitude.isnot(None)
            ).all()
            predictor.train(reports)
        ml_prediction = predictor.predict(lat, lon, profile)

    # ── 4. Seasonal info ──────────────────────────────────────────────────────
    season_info = _get_season_info(month)
    month_boost = MONTH_RISK_BOOST.get(month, 0.0)
    seasonal_risk_score = city_profile_data.get("risk_score", 0.35) + month_boost if city_profile_data else month_boost + 0.30
    seasonal_risk_score = round(min(seasonal_risk_score, 1.0), 3)

    # ── 5. City-specific review-based insights ────────────────────────────────
    city_stats = None
    if city_profile_data:
        peak_months = city_profile_data.get("peak_complaint_months", [])
        city_stats = {
            "city":                  city,
            "total_reviews":         city_profile_data.get("total_reviews", 0),
            "negative_reviews":      city_profile_data.get("negative_reviews", 0),
            "avg_rating":            city_profile_data.get("avg_rating", 4.0),
            "scam_mentions":         city_profile_data.get("scam_mentions", 0),
            "top_location_types":    city_profile_data.get("top_location_types", {}),
            "peak_complaint_months": [_MONTH_NAMES.get(m, str(m)) for m in peak_months],
            "risk_score":            city_profile_data.get("risk_score", 0.35),
            "is_peak_complaint_month": month in peak_months,
        }

    # ── 6. Pattern alerts (city-specific from insights JSON) ─────────────────
    all_patterns = insights.get("patterns", [])
    city_patterns = []
    if city:
        city_lower = city.lower()
        city_patterns = [
            p for p in all_patterns
            if city_lower in p.get("city", "").lower()
        ][:5]
    else:
        city_patterns = all_patterns[:5]

    # ── 7. Radar chart data — 6 risk categories ───────────────────────────────
    transport_risk = _threat_score(threat_scores, ["Tuk Tuk Scam", "Transport Fraud"])
    scam_risk      = _threat_score(threat_scores, ["Gem Scam", "Overcharging", "Fake Guide", "Food/Menu Scam", "Accommodation Scam"])
    safety_risk    = _threat_score(threat_scores, ["Harassment", "Physical Assault", "Theft / Robbery"])
    health_risk    = _threat_score(threat_scores, ["Health / Hygiene"])
    hazard_risk    = _threat_score(threat_scores, ["Accident / Hazard", "Unsafe Area"])
    seasonal_radar = round(min(month_boost * 3, 1.0), 3)

    radar = {
        "Transport":  round(min(transport_risk * 1.5, 1.0), 3),
        "Scams":      round(min(scam_risk * 1.3, 1.0), 3),
        "Safety":     round(min(safety_risk * 1.4, 1.0), 3),
        "Health":     round(min(health_risk * 2.0, 1.0), 3),
        "Hazards":    round(min(hazard_risk * 2.0, 1.0), 3),
        "Seasonal":   seasonal_radar,
    }

    # ── 8. Overall safety score ───────────────────────────────────────────────
    avg_radar = sum(radar.values()) / len(radar)
    overall_safety = round(max(0, 100 - avg_radar * 100))
    risk_label = "High Risk" if overall_safety < 40 else ("Moderate Risk" if overall_safety < 70 else "Generally Safe")

    # ── 9. Personalised checklist ─────────────────────────────────────────────
    checklist = _build_checklist(profile, city, month, top_threats)

    return {
        "profile":          profile,
        "profile_icon":     _PROFILE_ICONS.get(profile, "🌍"),
        "city":             city,
        "month":            month,
        "month_name":       _MONTH_NAMES.get(month, ""),
        "season":           season_info,
        "overall_safety_score": overall_safety,
        "risk_label":       risk_label,
        "radar":            radar,
        "top_threats":      threats_list,
        "safety_tips":      tips,
        "checklist":        checklist,
        "pattern_alerts":   city_patterns,
        "city_stats":       city_stats,
        "ml_prediction":    ml_prediction,
        "seasonal_risk":    {
            "score": seasonal_risk_score,
            "month_boost": month_boost,
            "is_high_season": month_boost >= 0.15,
        },
    }


@router.get("/patterns")
def get_patterns(
    limit: int = Query(30, ge=1, le=100),
    city: Optional[str] = Query(None),
    month: Optional[int] = Query(None, ge=1, le=12),
):
    """Returns ML-discovered recurring incident patterns from Reviews.csv."""
    analyzer = get_analyzer()
    patterns = analyzer.get_top_patterns(100)

    if city:
        city_lower = city.lower()
        patterns = [p for p in patterns if city_lower in p.get("city", "").lower()]

    if month:
        patterns = [p for p in patterns if p.get("month") == month]

    return {"patterns": patterns[:limit], "total": len(patterns)}


@router.get("/seasonal-calendar")
def get_seasonal_calendar(city: Optional[str] = Query(None)):
    """
    Returns month-by-month risk index for cities.
    Used to render the seasonal safety calendar in the UI.
    """
    analyzer = get_analyzer()
    insights = _get_insights()

    if city:
        # Single city calendar
        city_seasonal = analyzer.seasonal_risk.get(city, {})
        # Fill missing months with global boost
        calendar = []
        for m in range(1, 13):
            risk = city_seasonal.get(m, MONTH_RISK_BOOST.get(m, 0.0) + 0.30)
            calendar.append({
                "month": m,
                "month_name": _MONTH_NAMES[m],
                "risk_score": round(risk, 4),
                "season": _get_season_info(m)["label"],
                "season_icon": _get_season_info(m)["icon"],
            })
        return {"city": city, "calendar": calendar}

    # All cities — return top 15 cities by review count
    city_profiles = insights.get("city_profiles", analyzer.city_scam_profile)
    top_cities = sorted(
        city_profiles.items(),
        key=lambda x: x[1].get("total_reviews", 0),
        reverse=True
    )[:15]

    result = {}
    for city_name, profile in top_cities:
        city_seasonal = analyzer.seasonal_risk.get(city_name, {})
        result[city_name] = [
            {
                "month": m,
                "month_name": _MONTH_NAMES[m],
                "risk_score": round(city_seasonal.get(m, MONTH_RISK_BOOST.get(m, 0.0) + 0.30), 4),
            }
            for m in range(1, 13)
        ]

    return {"cities": result}


@router.get("/location-types")
def get_location_type_risks():
    """Returns risk breakdown by venue/location type (beaches, temples, markets, etc.)."""
    analyzer = get_analyzer()
    insights = _get_insights()

    loc_type_risk = insights.get("location_type_risk", analyzer.location_type_risk)
    if not loc_type_risk:
        loc_type_risk = LOCATION_TYPE_BASE_RISK

    result = []
    for loc_type, risk in sorted(loc_type_risk.items(), key=lambda x: -x[1]):
        safety = round(100 - risk * 100)
        result.append({
            "location_type": loc_type,
            "risk_score": round(risk, 4),
            "safety_score": safety,
            "risk_label": "High" if risk > 0.55 else ("Moderate" if risk > 0.35 else "Low"),
            "base_risk": round(LOCATION_TYPE_BASE_RISK.get(loc_type, 0.40), 4),
        })
    return {"location_types": result}


@router.get("/city-profile")
def get_city_profile(city: str = Query(..., description="City name")):
    """Returns detailed review-based safety profile for a specific city."""
    analyzer = get_analyzer()
    insights = _get_insights()

    city_profiles = insights.get("city_profiles", analyzer.city_scam_profile)
    profile = city_profiles.get(city)
    if not profile:
        # Try partial match
        city_lower = city.lower()
        for k, v in city_profiles.items():
            if city_lower in k.lower():
                profile = v
                city = k
                break

    if not profile:
        return {"city": city, "found": False, "message": "No review data for this city."}

    # Add seasonal data
    seasonal = analyzer.seasonal_risk.get(city, {})
    peak_months = profile.get("peak_complaint_months", [])
    safe_months = [m for m in range(1, 13) if m not in peak_months and MONTH_RISK_BOOST.get(m, 0) < 0.10]

    return {
        "city":                    city,
        "found":                   True,
        "total_reviews":           profile.get("total_reviews", 0),
        "negative_reviews":        profile.get("negative_reviews", 0),
        "avg_rating":              profile.get("avg_rating", 4.0),
        "scam_mentions":           profile.get("scam_mentions", 0),
        "risk_score":              profile.get("risk_score", 0.35),
        "safety_score":            round(100 - profile.get("risk_score", 0.35) * 100),
        "top_location_types":      profile.get("top_location_types", {}),
        "peak_complaint_months":   [{"month": m, "name": _MONTH_NAMES[m]} for m in peak_months],
        "recommended_months":      [{"month": m, "name": _MONTH_NAMES[m]} for m in safe_months[:4]],
        "lat":                     profile.get("lat"),
        "lon":                     profile.get("lon"),
        "monthly_risk":            [
            {"month": m, "name": _MONTH_NAMES[m], "risk": round(seasonal.get(m, 0.30), 4)}
            for m in range(1, 13)
        ],
    }
@router.get("/real-reports")
def get_real_reports(
    city: str = Query(..., description="City name to search"),
    profile: Optional[str] = Query(None, description="Filter by demographic target"),
    limit: int = Query(8, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """
    Returns actual incident titles and sources from the DB for a given city.
    Used by the AI Advisor to show 'What tourists actually reported' section.
    """
    query = (
        db.query(Report)
        .filter(Report.location_name.ilike(f"%{city}%"))
        .filter(Report.title.isnot(None))
        .filter(Report.risk_level >= 2)  # Only moderate/high risk
        .order_by(Report.risk_level.desc(), Report.created_at.desc())
        .limit(limit)
    )

    reports = query.all()

    # Map source names to readable labels and user-friendly credibility categories
    SOURCE_LABELS = {
        "adaderana": "Ada Derana", "sundaytimes": "Sunday Times",
        "daily_mirror": "Daily Mirror", "google_news": "Google News",
        "colombo_gazette": "Colombo Gazette", "newsfirst": "Newsfirst",
        "ceylon_today": "Ceylon Today", "themorning_lk": "The Morning",
        "hirunews_lk": "Hiru News", "theisland_lk": "The Island",
        "economynext_lk": "Economy Next", "newswire_lk": "Newswire",
        "reddit": "Reddit", "youtube": "YouTube", "facebook": "Facebook",
        "google_maps": "Google Maps", "tripadvisor": "TripAdvisor",
    }
    TRUSTED_SOURCES = {
        "adaderana", "sundaytimes", "daily_mirror", "google_news",
        "colombo_gazette", "newsfirst", "ceylon_today", "themorning_lk",
        "hirunews_lk", "theisland_lk", "economynext_lk", "newswire_lk",
    }
    RISK_LABELS = {"": "Unknown", 1: "Low", 2: "Moderate", 3: "High"}

    def get_cred_weight(src: str) -> float:
        s = (src or "").lower()
        if s in TRUSTED_SOURCES or "news" in s:
            return 0.90
        if "tripadvisor" in s or "maps" in s:
            return 0.70
        return 0.40

    def get_cred_label(src: str) -> str:
        s = (src or "").lower()
        if s in TRUSTED_SOURCES or "news" in s:
            return "🏛️ Verified News Outlets"
        if "tripadvisor" in s or "maps" in s:
            return "🟢 Verified Traveler Reviews"
        return "💬 Public Community Discussion"

    # Primary sort: 1) Source Credibility Weight (descending), 2) Risk Level (descending)
    sorted_reports = sorted(reports, key=lambda r: (-get_cred_weight(r.source), -(r.risk_level or 1)))

    return {
        "city": city,
        "total_found": len(sorted_reports),
        "reports": [
            {
                "id": r.id,
                "title": (r.title or "")[:150],
                "source": r.source,
                "source_label": SOURCE_LABELS.get(r.source or "", r.source or "Unknown"),
                "credibility_label": get_cred_label(r.source),
                "is_verified_source": (r.source or "").lower() in TRUSTED_SOURCES,
                "scam_type": r.scam_type,
                "risk_level": r.risk_level,
                "risk_label": RISK_LABELS.get(r.risk_level, "Unknown"),
                "url": r.url if r.url and r.url.startswith("http") else None,
                "location": r.location_name,
                "date": str(r.created_at.date()) if r.created_at else None,
            }
            for r in sorted_reports
        ],
    }

def _threat_score(threat_scores: Dict[str, float], scam_types: List[str]) -> float:
    vals = [threat_scores.get(t, 0.0) for t in scam_types]
    return round(sum(vals) / len(scam_types), 4) if vals else 0.0


def _build_checklist(
    profile: str, city: Optional[str], month: int, top_threats: list
) -> List[Dict]:
    """Build an actionable pre-trip safety checklist tailored to the user."""
    items = []

    # Always-on universal items
    items.append({
        "category": "Emergency",
        "icon": "🆘",
        "task": "Save Tourist Police number: 1912",
        "priority": "critical",
    })
    items.append({
        "category": "Emergency",
        "icon": "📱",
        "task": "Download PickMe app for safe taxis in major cities",
        "priority": "high",
    })

    # Profile-specific
    if profile == "Solo Female":
        items += [
            {"category": "Personal Safety", "icon": "📍", "task": "Share live GPS with someone trusted", "priority": "critical"},
            {"category": "Accommodation", "icon": "🏨", "task": "Pre-book accommodation — don't let strangers redirect you", "priority": "high"},
            {"category": "Dress", "icon": "👗", "task": "Pack a scarf/shawl for temple visits", "priority": "medium"},
        ]
    elif profile == "Family":
        items += [
            {"category": "Health", "icon": "💊", "task": "Pack oral rehydration salts, antihistamines, sunscreen", "priority": "critical"},
            {"category": "Health", "icon": "🦟", "task": "Apply DEET mosquito repellent daily — dengue risk is real", "priority": "high"},
            {"category": "Safety", "icon": "🌊", "task": "Check beach flags daily — rip currents at many beaches", "priority": "high"},
            {"category": "Child Safety", "icon": "👶", "task": "Wristband with parent's phone number for children in markets", "priority": "medium"},
        ]
    elif profile in ("Solo Male", "General"):
        items += [
            {"category": "Scams", "icon": "💎", "task": "Refuse all gem shop invitations from tuk-tuk drivers", "priority": "high"},
            {"category": "Transport", "icon": "🚕", "task": "Use airport pre-paid taxi counter only — avoid touts", "priority": "high"},
        ]
    elif profile == "Couple":
        items += [
            {"category": "Scams", "icon": "💎", "task": "Never enter gem shops — couples are prime investment scam targets", "priority": "high"},
            {"category": "Accommodation", "icon": "🏨", "task": "Confirm hotel directly before arriving", "priority": "medium"},
        ]
    elif profile == "Group":
        items += [
            {"category": "Finance", "icon": "💰", "task": "Designate one person to check all group bills", "priority": "high"},
            {"category": "Transport", "icon": "🚌", "task": "Book group transport through hotel — avoid station touts", "priority": "high"},
        ]

    # Top threat items
    for t, score in top_threats[:3]:
        if score > 0.15:
            items.append({
                "category": "Threat Alert",
                "icon": "⚠️",
                "task": f"High chance of {t} in {city or 'Sri Lanka'} — stay alert",
                "priority": "high" if score > 0.4 else "medium",
            })

    # Seasonal
    if MONTH_RISK_BOOST.get(month, 0) >= 0.15:
        items.append({
            "category": "Weather",
            "icon": "🌧️",
            "task": f"Monsoon season in {_MONTH_NAMES.get(month, 'this month')} — check road/attraction closures",
            "priority": "medium",
        })

    # Transport universal
    items.append({
        "category": "Transport",
        "icon": "🛺",
        "task": "Always negotiate tuk-tuk fare BEFORE getting in",
        "priority": "high",
    })

    # Deduplicate by task text and sort by priority
    seen = set()
    unique_items = []
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    for item in sorted(items, key=lambda x: priority_order.get(x["priority"], 9)):
        if item["task"] not in seen:
            seen.add(item["task"])
            unique_items.append(item)

    return unique_items
