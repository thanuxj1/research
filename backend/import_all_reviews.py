"""
Full CSV Import — All Ratings from Reviews.csv + canonical_destinations.csv
============================================================================
- Imports ALL 16,156 reviews (1-5 stars) from Reviews.csv
  * 1-2 star: risk_level=3/2, is_scam=True (active safety signal)
  * 3 star:   risk_level=2, is_scam=False (moderate, ambiguous)
  * 4-5 star: risk_level=1, is_scam=False (positive context, can improve location coverage)
- Uses canonical_destinations.csv to enrich location coordinates
- Lightweight keyword NLP — no transformer models (avoids OOM)
- Deduplicates against existing DB content
IT22629180
"""
import sys, os, csv, sqlite3
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.db.models import Report, RiskZone
from app.ml.clustering_service import ClusteringService

# ── Primary coordinate map (directly known cities) ────────────────────────────
CITY_COORDS = {
    "Ahangama":        (5.9706,  80.3574),
    "Ambalangoda":     (6.2348,  80.0551),
    "Anuradhapura":    (8.3114,  80.4037),
    "Arugam Bay":      (6.8399,  81.8325),
    "Bentota":         (6.4208,  80.0006),
    "Beruwala":        (6.4801,  79.9838),
    "Colombo":         (6.9271,  79.8612),
    "Deniyaya":        (6.3465,  80.5664),
    "Ella":            (6.8667,  81.0466),
    "Embilipitiya":    (6.3433,  80.8447),
    "Galle":           (6.0535,  80.2210),
    "Habarana":        (8.0097,  80.7489),
    "Haputale":        (6.7681,  80.9603),
    "Hikkaduwa":       (6.1395,  80.1008),
    "Jaffna":          (9.6615,  80.0255),
    "Kalkudah":        (8.0000,  81.3667),
    "Kalutara":        (6.5854,  79.9607),
    "Kandy":           (7.2906,  80.6337),
    "Katukitula":      (7.3833,  80.7000),
    "Koslanda":        (6.7167,  80.9167),
    "Mirissa":         (5.9483,  80.4716),
    "Negombo":         (7.2083,  79.8358),
    "Nilaveli":        (8.7167,  81.2000),
    "Nuwara Eliya":    (6.9497,  80.7891),
    "Peradeniya":      (7.2667,  80.5933),
    "Pinnawala":       (7.3000,  80.3833),
    "Polonnaruwa":     (7.9403,  81.0188),
    "Pussellawa":      (7.0667,  80.6333),
    "Saliyapura":      (8.3667,  80.4167),
    "Sigiriya":        (7.9572,  80.7603),
    "Tissamaharama":   (6.2833,  81.2833),
    "Trincomalee":     (8.5922,  81.2152),
    "Unawatuna":       (5.9997,  80.2489),
    "Weligatta":       (6.1000,  80.4000),
    # Additional coverage
    "Dambulla":        (7.8742,  80.6511),
    "Matara":          (5.9549,  80.5550),
    "Tangalle":        (6.0241,  80.7982),
    "Weligama":        (5.9736,  80.4276),
    "Passikudah":      (7.9333,  81.5500),
    "Hambantota":      (6.1241,  81.1185),
    "Badulla":         (6.9895,  81.0557),
    "Ratnapura":       (6.6828,  80.3992),
    "Gampaha":         (7.0913,  80.0128),
    "Kurunegala":      (7.4863,  80.3647),
    "Puttalam":        (8.0362,  79.8283),
    "Mannar":          (8.9779,  79.9041),
    "Vavuniya":        (8.7514,  80.4972),
    "Batticaloa":      (7.7170,  81.6924),
    "Ampara":          (7.2952,  81.6725),
    "Monaragala":      (6.8726,  81.3504),
    "Kegalle":         (7.2515,  80.3464),
    "Nuwara":          (6.9497,  80.7891),
    "Beruwela":        (6.4801,  79.9838),
    "Wennappuwa":      (7.3617,  79.8506),
}

# ── Load canonical destinations for extra coordinate coverage ─────────────────
CANONICAL_COORDS = {}
_canon_path = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "canonical_destinations.csv")
)
if os.path.exists(_canon_path):
    # Use approximate province/category coords as fallbacks
    _PROVINCE_COORDS = {
        "North Central": (8.0000, 80.6000),
        "Central": (7.2906, 80.6337),
        "Southern": (6.0535, 80.2210),
        "Western": (6.9271, 79.8612),
        "North Western": (7.4863, 80.3647),
        "Eastern": (7.7170, 81.6924),
        "Northern": (9.6615, 80.0255),
        "Sabaragamuwa": (6.6828, 80.3992),
        "Uva": (6.9895, 81.0557),
    }
    with open(_canon_path, encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get('destination_name') or '').strip()
            province = (row.get('province') or '').strip()
            alts = [a.strip() for a in (row.get('alt_names') or '').split(';') if a.strip()]
            prov_coord = _PROVINCE_COORDS.get(province)
            if prov_coord and name:
                CANONICAL_COORDS[name.lower()] = prov_coord
                for alt in alts:
                    CANONICAL_COORDS[alt.lower()] = prov_coord

def get_coords(city: str, location_str: str):
    """Resolve coordinates: try exact city, then canonical lookup, then province fallback."""
    # 1. Direct city match
    c = CITY_COORDS.get(city)
    if c:
        return c
    # 2. Canonical lookup (by city name)
    c = CANONICAL_COORDS.get(city.lower())
    if c:
        return c
    # 3. Try first word of location string
    if location_str:
        first = location_str.split(',')[0].strip()
        c = CITY_COORDS.get(first) or CANONICAL_COORDS.get(first.lower())
        if c:
            return c
    return (None, None)

# ── Lightweight keyword NLP ───────────────────────────────────────────────────
SCAM_KEYWORDS = {
    "gem_scam":           ["gem scam","fake gem","gem shop","overpriced gem","ruby scam","sapphire","moonstone scam","fake jewel","fake stone"],
    "tuk_tuk_scam":       ["tuk tuk","tuk-tuk","tuktuk","three-wheeler","three wheeler","tuk overcharged","tuk rip"],
    "commission_shop":    ["commission shop","took me to a shop","took us to a shop","spice garden","forced to buy","driver commission"],
    "overcharging":       ["overcharged","ripped off","double price","tourist price","too expensive","charged extra","inflated price","extortion","rip off","ripoff"],
    "fake_guide":         ["fake guide","unofficial guide","unauthorized guide","demanded money","fake monk","not licensed guide"],
    "transport_fraud":    ["taxi scam","refused meter","tampered meter","agreed price changed","wrong route","airport taxi","train ticket tout"],
    "accommodation_scam": ["hotel scam","different room","bait switch","fake booking","different property","dirty room","no refund"],
    "food_scam":          ["fake menu","surprise bill","tourist menu","service charge scam","overcharged food","no menu price"],
    "theft":              ["stolen","pickpocket","mugged","robbed","bag snatched","phone stolen","passport stolen"],
    "harassment":         ["harassed","followed me","uncomfortable","touched me","catcalling","stalked","groped","beach boy"],
    "unsafe_area":        ["unsafe","dangerous area","avoid at night","sketchy","threatened","intimidated"],
}

GENERAL_SCAM_WORDS = ["scam","fraud","cheat","deceive","deceptive","swindle","lied","dishonest","con ","con man"]

def classify_text(text: str):
    t = text.lower()
    for scam_type, keywords in SCAM_KEYWORDS.items():
        if any(kw in t for kw in keywords):
            return scam_type, True
    if any(w in t for w in GENERAL_SCAM_WORDS):
        return "overcharging", True
    return None, False

NEG_WORDS = ["terrible","awful","horrible","worst","disgusting","scam","fraud","angry","furious",
             "ripped","cheated","lied","dishonest","waste","refused","demanded","overcharged",
             "broken","filthy","dangerous","avoid","never again","nightmare","regret","dirty","unsafe"]
POS_WORDS = ["good","great","excellent","nice","pleasant","helpful","clean","safe","recommend",
             "worth","beautiful","stunning","amazing","wonderful","loved","perfect","fantastic"]

def simple_sentiment(text: str, rating: int) -> float:
    t = text.lower()
    score = sum(-0.8 for w in NEG_WORDS if w in t) + sum(0.5 for w in POS_WORDS if w in t)
    # Bias by star rating
    rating_bias = {1: -0.8, 2: -0.4, 3: 0.0, 4: 0.3, 5: 0.7}.get(rating, 0.0)
    return max(-1.0, min(1.0, (score / 5.0) + rating_bias))


def run_import():
    print("=" * 65)
    print("  Full CSV Import — All Ratings (1-5 stars)")
    print("=" * 65)

    db = SessionLocal()

    csv_path = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Reviews.csv")
    )
    if not os.path.exists(csv_path):
        print(f"[ERROR] Reviews.csv not found at: {csv_path}")
        db.close()
        return

    print(f"Reading: {csv_path}")
    with open(csv_path, encoding="latin-1", errors="replace") as f:
        reader = csv.DictReader(f)
        all_rows = list(reader)

    print(f"Total rows in CSV : {len(all_rows)}")

    # Rating breakdown
    from collections import Counter
    rating_counts = Counter(r.get('Rating','').strip() for r in all_rows)
    for k in sorted(rating_counts):
        print(f"  {k} stars: {rating_counts[k]}")

    # Pre-load existing content fingerprints to skip duplicates
    print("\nLoading existing DB fingerprints...")
    existing = db.query(Report.content).all()
    existing_fps = {(c[0] or '')[:120].lower().strip() for c in existing}
    print(f"Existing reports in DB: {len(existing_fps)}")

    saved = skipped_dup = skipped_short = errors = 0
    saved_by_rating = Counter()

    for i, row in enumerate(all_rows):
        try:
            title        = (row.get("Title")        or "").strip()
            content      = (row.get("Text")         or "").strip()
            city         = (row.get("Located_City") or "").strip()
            location_str = (row.get("Location")     or city).strip()
            rating_str   = (row.get("Rating", "")   or "").strip()

            if not content or len(content) < 20:
                skipped_short += 1
                continue

            full_text = f"{title}. {content}".strip() if title else content

            # Deduplicate
            fp = full_text[:120].lower().strip()
            if fp in existing_fps:
                skipped_dup += 1
                continue
            existing_fps.add(fp)

            # Parse rating
            try:
                rating = int(float(rating_str))
            except (ValueError, TypeError):
                rating = 3

            # Coordinates
            lat, lon = get_coords(city, location_str)

            # Classification
            scam_type, is_scam = classify_text(full_text)
            sentiment_score    = simple_sentiment(full_text, rating)

            # Risk level by star rating
            if rating == 1:
                risk_level = 3
            elif rating == 2:
                risk_level = 2
            elif rating == 3:
                risk_level = 2
                is_scam = is_scam  # only if keywords found
            else:
                # 4-5 star: low risk, not scam unless explicit keywords
                risk_level = 1
                is_scam = is_scam and any(
                    kw in full_text.lower()
                    for kw in ["scam","fraud","theft","stolen","robbed","harassed","dangerous"]
                )

            # Helpful votes
            try:
                helpful_votes = int(float(str(row.get("Helpful_Votes", "0") or "0").strip()))
            except (ValueError, TypeError):
                helpful_votes = 0

            report = Report(
                source          = "tripadvisor_csv",
                url             = None,
                title           = title or (scam_type.replace("_"," ").title() if scam_type else f"Review — {city}"),
                content         = full_text,
                latitude        = lat,
                longitude       = lon,
                is_scam         = is_scam,
                scam_type       = scam_type,
                risk_level      = risk_level,
                sentiment_score = sentiment_score,
                location_name   = location_str or city,
                demographic_target = None,
                helpful_votes   = helpful_votes,
            )
            db.add(report)
            saved += 1
            saved_by_rating[rating_str] += 1

            if saved % 200 == 0:
                db.commit()
                print(f"  Saved {saved} / {len(all_rows) - skipped_dup - skipped_short} ...")

        except Exception as e:
            errors += 1
            db.rollback()
            if errors <= 5:
                print(f"  [Error] Row {i}: {e}")

    db.commit()
    print(f"\n--- Import Complete ---")
    print(f"  Saved      : {saved}")
    print(f"  Skipped    : {skipped_dup} duplicates + {skipped_short} too short")
    print(f"  Errors     : {errors}")
    print(f"  By rating  : {dict(sorted(saved_by_rating.items()))}")

    # Recluster risk zones
    print("\nRecalculating risk zones...")
    db.query(RiskZone).delete()
    db.commit()
    try:
        zones = ClusteringService(eps_km=2.0, min_samples=3).run(db)
        print(f"[OK] Risk zones updated: {zones} zones")
    except Exception as e:
        print(f"[Clustering Error] {e}")

    db.close()

    # Final DB count
    conn = sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), "safety_heatmap.db"))
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM reports")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM reports WHERE source='tripadvisor_csv'")
    ta = cur.fetchone()[0]
    conn.close()
    print(f"\n[DB] Total reports: {total}  |  tripadvisor_csv: {ta}")


if __name__ == "__main__":
    run_import()
