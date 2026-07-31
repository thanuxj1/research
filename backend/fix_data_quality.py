"""
Data Quality Fixer for SafeTravel LK
- Step 1: Remove clearly irrelevant posts (not tourism/safety related)
- Step 2: Re-classify remaining posts that are missing scam_type or location
"""
import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.db.models import Report
from app.ml.nlp_pipeline import NLPPipeline, TOURISM_KEYWORDS, SCAM_TAXONOMY

# Expanded location dictionary to catch more places
EXPANDED_LOCATIONS = {
    "colombo": (6.9271, 79.8612),
    "colombo fort": (6.9344, 79.8428),
    "kandy": (7.2906, 80.6337),
    "galle": (6.0535, 80.2210),
    "galle fort": (6.0535, 80.2210),
    "ella": (6.8728, 81.0464),
    "sigiriya": (7.9573, 80.7600),
    "negombo": (7.2083, 79.8358),
    "mirissa": (5.9483, 80.4716),
    "arugam bay": (6.8399, 81.8325),
    "nuwara eliya": (6.9497, 80.7891),
    "trincomalee": (8.5874, 81.2152),
    "hikkaduwa": (6.1395, 80.1061),
    "unawatuna": (5.9997, 80.2489),
    "bentota": (6.4221, 80.0009),
    "matara": (5.9549, 80.5550),
    "jaffna": (9.6615, 80.0255),
    "anuradhapura": (8.3114, 80.4037),
    "polonnaruwa": (7.9396, 81.0009),
    "dambulla": (7.8675, 80.6517),
    "pinnawala": (7.3014, 80.3844),
    "airport": (7.1806, 79.8841),
    "pettah": (6.9358, 79.8535),
    "weligama": (5.9748, 80.4282),
    "mount lavinia": (6.8297, 79.8661),
    "tangalle": (6.0252, 80.7960),
    "tissamaharama": (6.2833, 81.2833),
    "yala": (6.3667, 81.5167),
    "haputale": (6.7667, 80.9667),
    "badulla": (6.9931, 81.0549),
    "hatton": (6.8939, 80.5956),
    "nuwara": (6.9497, 80.7891),
    "pettah market": (6.9358, 79.8535),
    "temple of tooth": (7.2936, 80.6413),
    "nine arch bridge": (6.8770, 81.0590),
    "sri lanka": (7.8731, 80.7718),
    "ceylon": (7.8731, 80.7718),
}

# Keywords that indicate a post is NOT tourism-safety related
IRRELEVANT_PATTERNS = [
    "a/l exam", "o/l exam", "a/l result", "o/l result",
    "11.11 sale", "reshared from facebook",
    "studying in colombo", "sitting exam",
    "justpay", "viber message",  # these are generic scam refs
]

def is_tourism_relevant(text: str) -> bool:
    """Check if the post is relevant to tourism safety."""
    text_lower = text.lower()
    # Must contain at least one tourism keyword
    has_tourism = any(kw in text_lower for kw in TOURISM_KEYWORDS)
    # Must not be an obviously irrelevant post
    has_irrelevant = any(pat in text_lower for pat in IRRELEVANT_PATTERNS)
    return has_tourism and not has_irrelevant

def extract_location_expanded(text: str):
    """More aggressive location extraction."""
    text_lower = text.lower()
    for place, coords in EXPANDED_LOCATIONS.items():
        if place in text_lower:
            return coords[0], coords[1], place.title()
    return None, None, None

def detect_scam_type_expanded(text: str):
    """Detect scam type using expanded taxonomy."""
    text_lower = text.lower()
    hits = {}
    for stype, keywords in SCAM_TAXONOMY.items():
        matched = [kw for kw in keywords if kw in text_lower]
        if matched:
            hits[stype] = len(matched)
    if not hits:
        # Try broader fallback terms
        if any(w in text_lower for w in ["ripped", "cheated", "fraud", "stole", "stolen", "overcharg"]):
            return "overcharging"
        if any(w in text_lower for w in ["scam", "fake", "swindl"]):
            return "overcharging"
        return None
    return max(hits, key=hits.get)


def fix_data_quality():
    print("=" * 60)
    print("  SafeTravel LK — Data Quality Fixer")
    print("=" * 60)

    db = SessionLocal()
    
    # Step 1: Remove irrelevant reports
    print("\n[Step 1] Scanning for irrelevant posts...")
    all_reports = db.query(Report).all()
    removed = 0
    for r in all_reports:
        content = (r.content or "").strip()
        title = (r.title or "").strip()
        full_text = f"{title} {content}".lower()
        
        if not is_tourism_relevant(full_text):
            db.delete(r)
            removed += 1
    
    db.commit()
    print(f"  Removed {removed} irrelevant posts.")

    # Step 2: Re-analyze remaining reports missing type/location
    print("\n[Step 2] Re-classifying reports with missing fields...")
    needs_fix = db.query(Report).filter(
        (Report.scam_type.is_(None)) | (Report.location_name.is_(None))
    ).all()

    print(f"  Found {len(needs_fix)} reports needing enrichment...")

    updated = 0
    for r in needs_fix:
        full_text = f"{r.title or ''} {r.content or ''}".lower()

        # Try expanded location detection
        if not r.location_name:
            lat, lon, loc = extract_location_expanded(full_text)
            if loc:
                r.latitude = lat
                r.longitude = lon
                r.location_name = loc

        # Try expanded scam type detection
        if not r.scam_type:
            stype = detect_scam_type_expanded(full_text)
            if stype:
                r.scam_type = stype
                r.is_scam = True
                if r.risk_level == 1:
                    r.risk_level = 2

        updated += 1
        if updated % 200 == 0:
            db.commit()
            print(f"  Processed {updated}/{len(needs_fix)}...")

    db.commit()
    
    # Final count
    final_total = db.query(Report).count()
    final_no_type = db.query(Report).filter(Report.scam_type.is_(None)).count()
    final_no_loc = db.query(Report).filter(Report.location_name.is_(None)).count()
    
    print(f"\n{'='*60}")
    print(f"  DONE!")
    print(f"  Total reports remaining:  {final_total}")
    print(f"  Still missing scam_type:  {final_no_type} ({final_no_type*100//max(final_total,1)}%)")
    print(f"  Still missing location:   {final_no_loc} ({final_no_loc*100//max(final_total,1)}%)")
    print(f"{'='*60}")

    db.close()

if __name__ == "__main__":
    fix_data_quality()
