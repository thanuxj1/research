"""
Authority & Security Dispatch API endpoint — IT22629180
Allows sharing verified scam alerts and threat briefings with
the Sri Lanka Tourist Police Division (Hotline 1912) and SLTDA.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Optional, List
from datetime import datetime, timezone
from app.db.session import get_db
from app.db.models import Report
from app.core.clustering import get_grid_zones
from app.ml.source_weights import SL_CERTIFIED_NEWS_SOURCES, GOVERNMENT_SOURCES, get_weight_tier_label

TRUSTED_NEWS_SOURCES = list(SL_CERTIFIED_NEWS_SOURCES.keys()) + list(GOVERNMENT_SOURCES.keys())

router = APIRouter()

PREVENTIVE_GUIDANCE_CATALOG = {
    "tuk_tuk_scam": {
        "title": "Tuk-Tuk Overcharging & Detour Scam",
        "description": "Unmetered drivers target tourists near transit hubs and redirect them to high-commission shops.",
        "preventive_actions": [
            "Always insist on metered tuk-tuks or agree on the fare prior to boarding.",
            "Use ride-hailing apps like PickMe or Uber where available (Colombo, Kandy, Galle).",
            "Politely decline driver offers to visit 'special' gem, spice, or tea shops.",
            "Report unmetered/coercive drivers to Tourist Police Hotline 1912."
        ],
        "authority_recommendation": "Deploy mobile traffic police checkpoints at Colombo Fort, Kandy Railway Station, and Galle Fort to enforce meter usage."
    },
    "gem_scam": {
        "title": "Unlicensed Gem & Jewelry Investment Fraud",
        "description": "Tout cartels approach tourists with fake 'export tax loophole' or 'discount gem purchase' stories.",
        "preventive_actions": [
            "Never purchase gems as an investment based on recommendations from street touts or drivers.",
            "Purchase gems ONLY from dealers accredited by the National Gem and Jewellery Authority (NGJA).",
            "Request official authenticity certificates and international export documentation.",
            "Verify dealer license numbers with NGJA before payment."
        ],
        "authority_recommendation": "Conduct joint inspection raids by SLTDA and NGJA officers on unregistered gem outlets in Ratnapura, Kandy, and Colombo 03."
    },
    "fake_guide": {
        "title": "Unaccredited Tourist Guide Coercion",
        "description": "Unauthorized individuals approach tourists near cultural heritage sites posing as official guides.",
        "preventive_actions": [
            "Verify guide credentials: official guides wear government-issued SLTDA photo ID badges.",
            "Refuse 'free' walkthroughs that result in demands for exorbitant fees at the end.",
            "Book official guides directly through cultural triangle ticket counters (Sigiriya, Polonnaruwa, Anuradhapura)."
        ],
        "authority_recommendation": "Increase stationing of uniformed Tourist Police officers at Sigiriya rock entrance, Temple of the Tooth, and Galle Fort gates."
    },
    "overcharging": {
        "title": "Inflated Tourist Pricing & Menu Traps",
        "description": "Establishments display unpriced menus or add unauthorized service fees for foreign visitors.",
        "preventive_actions": [
            "Always ask to see an official menu with printed prices before ordering food or drinks.",
            "Carefully examine itemized bills for extra unlisted charges prior to settling payments.",
            "Retain printed receipts for dispute filing."
        ],
        "authority_recommendation": "Issue SLTDA compliance notices requiring dual price listing disclosure and mandatory itemized receipts."
    },
    "harassment": {
        "title": "Beach Harassment & Unsolicited Approaches",
        "description": "Persistent uninvited approaches targeting solo travellers on public beaches and nightlife strips.",
        "preventive_actions": [
            "Avoid isolated beach stretches after sunset (Mirissa, Unawatuna, Hikkaduwa, Arugam Bay).",
            "Travel in groups or share live location with trusted contacts via GPS.",
            "Contact Tourist Police Helpline 1912 immediately if feeling unsafe or followed."
        ],
        "authority_recommendation": "Deploy evening beach patrols by female Tourist Police officers in Mirissa, Hikkaduwa, and Arugam Bay."
    }
}

EMERGENCY_HELPLINES = {
    "tourist_police": {"name": "Sri Lanka Tourist Police Division", "number": "1912", "direct": "+94 11 242 1052"},
    "police_emergency": {"name": "General Police Emergency", "number": "119", "direct": "119"},
    "medical_ambulance": {"name": "Suwa Seriya National Ambulance Service", "number": "1990", "direct": "1990"},
    "sltda_headquarters": {"name": "Sri Lanka Tourism Development Authority", "number": "+94 11 242 6800", "website": "https://www.sltda.gov.lk"},
}


@router.get("/dispatch-briefing")
def get_authority_dispatch_briefing(
    min_risk: float = 0.5,
    verified_only: bool = False,
    db: Session = Depends(get_db),
):
    """
    Generates an official Security & Threat Intelligence Dispatch Briefing
    tailored for the Sri Lanka Tourist Police Division and SLTDA officers.
    """
    total_db_reports = db.query(func.count(Report.id)).filter(
        Report.latitude.isnot(None),
        Report.longitude.isnot(None)
    ).scalar() or 0

    # Fetch top incident locations efficiently
    top_locations = (
        db.query(
            Report.location_name,
            Report.scam_type,
            func.count(Report.id).label("cnt"),
            func.avg(Report.latitude).label("avg_lat"),
            func.avg(Report.longitude).label("avg_lon"),
            func.avg(Report.risk_level).label("avg_risk")
        )
        .filter(Report.location_name.isnot(None))
        .group_by(Report.location_name, Report.scam_type)
        .order_by(desc("cnt"))
        .limit(15)
        .all()
    )

    briefing_hotspots = []
    for i, r in enumerate(top_locations):
        scam_type = r[1] or "general"
        avg_risk_level = r[5] or 1.0
        risk_score = round(min(avg_risk_level / 3.0, 1.0), 3)

        guidance = PREVENTIVE_GUIDANCE_CATALOG.get(
            scam_type,
            {
                "title": "General Tourist Security Warning",
                "preventive_actions": ["Exercise heightened spatial awareness.", "Keep valuables secure.", "Call Tourist Police 1912 in emergency."],
                "authority_recommendation": "Deploy regular tourist security patrols in this area."
            }
        )

        briefing_hotspots.append({
            "hotspot_id": i + 1,
            "location_name": r[0],
            "center_coordinates": {"latitude": round(r[3], 4), "longitude": round(r[4], 4)},
            "risk_score": risk_score,
            "risk_classification": "CRITICAL" if risk_score >= 0.65 else "MODERATE WARNING",
            "total_incidents": r[2],
            "scam_category": scam_type,
            "category_title": guidance["title"],
            "recommended_preventive_actions": guidance["preventive_actions"],
            "police_action_brief": guidance["authority_recommendation"],
        })

    # Verified evidence stats
    trusted_list = list(TRUSTED_NEWS_SOURCES)
    verified_count = db.query(func.count(Report.id)).filter(
        Report.source.in_(trusted_list)
    ).scalar() or 0

    verified_ratio = round((verified_count / total_db_reports * 100), 2) if total_db_reports > 0 else 0.0

    return {
        "document_metadata": {
            "title": "Sri Lanka Tourist Security & Incident Dispatch Briefing",
            "target_agency": "Sri Lanka Tourist Police Division & SLTDA",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "system_version": "SafeTravel AI Engine v1.0.0 (IT22629180)",
            "classification": "OFFICIAL TOURIST SECURITY DISPATCH",
        },
        "executive_summary": {
            "total_geocoded_incidents_analyzed": total_db_reports,
            "verified_news_citations": verified_count,
            "provenance_confidence": f"{verified_ratio}% verified news citations (Tier 1 Mainstream News Outlets)",
            "active_high_risk_hotspots": len(briefing_hotspots),
            "primary_helpline": EMERGENCY_HELPLINES["tourist_police"]["number"],
        },
        "hotspots_requiring_enforcement": briefing_hotspots,
        "emergency_helplines": EMERGENCY_HELPLINES,
    }


@router.get("/preventive-guidance")
def get_preventive_guidance_catalog():
    """
    Returns the complete catalog of preventive guidance, safety rules,
    and emergency helpline numbers for tourists and tourism officers.
    """
    return {
        "catalog": PREVENTIVE_GUIDANCE_CATALOG,
        "helplines": EMERGENCY_HELPLINES,
    }
