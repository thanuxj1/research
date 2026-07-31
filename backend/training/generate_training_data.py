"""
Generate labeled training data from the 968 collected reports.
Uses keyword-based auto-labeling to create a proper training CSV.
IT22629180
"""
import sys, os, csv
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal, engine
from app.db.models import Base, Report
from sqlalchemy import text

# Scam keyword rules for auto-labeling
# Scam keyword rules for auto-labeling
SCAM_RULES = {
    "gem_scam":          ["gem scam", "fake gem", "gem shop scam", "gem store scam", "overpriced gem", "ruby scam", "sapphire scam", "moonstone scam", "fake jewel", "fake stone"],
    "tuk_tuk_scam":      ["tuk tuk scam", "tuk-tuk scam", "tuktuk scam", "three-wheeler scam", "tuk tuk overcharged", "tuk tuk driver lied", "tuk tuk refusal", "tuk tuk rip off"],
    "overcharging":      ["overcharged", "ripped off", "double price", "tourist price", "too expensive", "charged extra", "10x the price", "extortion"],
    "fake_guide":        ["fake guide", "unofficial guide", "not licensed guide", "fake monk", "blessing scam", "dress code scam"],
    "transport_fraud":   ["taxi scam", "refused meter", "tampered meter", "agreed price changed", "wrong route", "airport taxi scam", "train ticket tout"],
    "harassment":        ["harassed", "followed", "uncomfortable", "touched", "catcall", "stalked", "beach boy", "groped", "sexual harassment"],
    "accommodation_scam":["hotel scam", "different room", "bait switch", "fake booking", "fake guesthouse"],
    "food_scam":         ["fake menu", "surprise bill", "tourist menu", "food poison", "service charge scam"],
    "theft":             ["theft", "stolen", "pickpocket", "mugged", "robbed", "bag snatch", "room theft"],
    "currency_scam":     ["money exchange scam", "counterfeit note", "short-change scam", "fake note", "atm skim", "card clone"],
    "online_fraud":      ["fake website", "instagram scam", "whatsapp scam", "deposit scam", "phishing"],
    "wildlife_exploit":  ["elephant ride abuse", "turtle hatchery scam", "animal abuse", "bullhook"],
    "drug_setup":        ["drug setup", "planted drugs", "police bribe", "cannabis setup"],
    "commission_shop":   ["commission shop", "commission store", "driver commission", "shop commission", "took me to a shop", "took us to a shop", "spice garden scam", "forced to buy at shop"],
}

SAFETY_WORDS = [
    "scam", "scammed", "fraud", "warning", "danger", "unsafe", "avoid",
    "ripped off", "fake", "cheat", "corrupt", "theft", "harass", "threat",
]

POSITIVE_WORDS = [
    "beautiful", "wonderful", "amazing", "safe", "friendly", "recommend",
    "great experience", "loved", "perfect", "paradise", "helpful", "honest",
]

NON_SCAM_NEWS_SIGNALS = [
    "disaster management", "affected by floods", "heavy showers", "met dept",
    "meteorology", "sluice gates", "evacuation drills", "haj pilgrimage",
    "port agreement", "elections commissioner", "election official", "polling booth",
    "high commissioner", "deputy high commissioner", "land reforms commission",
    "presidential commission", "bribery commission", "human rights commission",
    "police commission", "cabinet sub committee", "french embassy", "un high commissioner",
    "general election", "presidential election", "parliament election", "ballot paper",
    "sarath fonseka", "lrc director", "disappearances to begin hearings"
]


NEGATION_PHRASES = [
    "not a scam", "is not a scam", "was not a scam", "wasn't a scam", "not scam",
    "no scam", "never a scam", "not fake", "was not fake", "no overcharging",
    "not overcharged", "no issues", "100% legitimate", "official guide", "not a trap"
]

NEUTRAL_TRAVEL_PHRASES = [
    "avoid crowds", "avoid the crowds", "avoid heat", "avoid the heat",
    "avoid midday", "avoid peak hours", "avoid peak season", "avoid queues",
    "avoid the queue", "avoid waiting", "avoid traffic", "avoid long lines"
]


def label_text(text_lower):
    """Auto-label a piece of text. Returns (is_scam, scam_type, sentiment)."""
    # 1. Non-scam news check
    if any(sig in text_lower for sig in NON_SCAM_NEWS_SIGNALS):
        return 0, "", 0.0

    # 2. Positive gem check
    if any(phrase in text_lower for phrase in ["hidden gem", "cultural gem", "architectural gem", "gem of a", "gem of an", "real gem"]):
        if not any(k in text_lower for k in SCAM_RULES["gem_scam"]):
            return 0, "", 0.2

    # Strip negated scam phrases (e.g., "(not a scam)", "official guide", "avoid crowds")
    clean_text = text_lower
    for phrase in (NEGATION_PHRASES + NEUTRAL_TRAVEL_PHRASES):
        clean_text = clean_text.replace(phrase, "")

    # 3. Check scam types
    matched_type = None
    max_hits = 0
    for stype, keywords in SCAM_RULES.items():
        hits = sum(1 for kw in keywords if kw in clean_text)
        if hits > max_hits:
            max_hits = hits
            matched_type = stype

    # General scam detection
    scam_word_count = sum(1 for w in SAFETY_WORDS if w in clean_text)
    pos_word_count = sum(1 for w in POSITIVE_WORDS if w in text_lower)

    is_scam = 1 if (matched_type or scam_word_count >= 2) else 0

    # Override: if clearly positive and no scam keywords
    if pos_word_count >= 2 and scam_word_count == 0:
        is_scam = 0
        matched_type = None

    # Simple sentiment
    if scam_word_count > pos_word_count:
        sentiment = round(-0.3 - (scam_word_count * 0.15), 2)
        sentiment = max(sentiment, -1.0)
    elif pos_word_count > scam_word_count:
        sentiment = round(0.3 + (pos_word_count * 0.15), 2)
        sentiment = min(sentiment, 1.0)
    else:
        sentiment = 0.0

    return is_scam, matched_type or "", sentiment


def generate():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    reports = db.query(Report).all()
    print(f"Processing {len(reports)} reports...")

    output_path = os.path.join(os.path.dirname(__file__), "dataset", "sample_data.csv")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    rows = []
    scam_count = 0
    safe_count = 0

    for r in reports:
        content = (r.content or "").strip()
        if len(content) < 20:
            continue

        # Truncate very long texts (YouTube transcripts)
        if len(content) > 2000:
            content = content[:2000]

        text_lower = content.lower()
        is_scam, scam_type, sentiment = label_text(text_lower)

        rows.append({
            "text": content.replace('"', "'"),  # CSV-safe
            "is_scam": is_scam,
            "scam_type": scam_type,
            "sentiment": sentiment,
        })

        if is_scam:
            scam_count += 1
        else:
            safe_count += 1

    # Write CSV
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["text", "is_scam", "scam_type", "sentiment"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nTraining data generated: {output_path}")
    print(f"  Total rows:  {len(rows)}")
    print(f"  Scam (1):    {scam_count}")
    print(f"  Safe (0):    {safe_count}")
    print(f"  Ratio:       {scam_count/(scam_count+safe_count)*100:.1f}% scam")

    db.close()


if __name__ == "__main__":
    generate()
