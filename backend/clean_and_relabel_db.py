"""
Database & Master Dataset Cleaning and Relabeling Script
SafeTravel LK — IT22629180

Purges false-positive scam flags caused by:
1. "gem" substring matching inside "management", "arrangement", "judgment", or positive "hidden gem" reviews.
2. "commission" keyword matching inside official government/diplomatic commissions (Elections Commission, Land Reforms Commission, High Commissioner, etc.).
3. General news (floods, weather forecasts, disaster management, port agreements, pilgrimages).
"""
import os
import sys
import re
import sqlite3
import pandas as pd

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
RESEARCH_DIR = os.path.dirname(BACKEND_DIR)

DB_PATH = os.path.join(BACKEND_DIR, "safety_heatmap.db")
PRIMARY_CSV_BACKEND = os.path.join(BACKEND_DIR, "training", "dataset", "primary_master_dataset_clean.csv")
PRIMARY_CSV_ROOT = os.path.join(RESEARCH_DIR, "primary_master_dataset_clean.csv")


NON_SCAM_NEWS_SIGNALS = [
    "disaster management", "affected by floods", "heavy showers", "met dept",
    "meteorology", "sluice gates", "evacuation drills", "haj pilgrimage",
    "port agreement", "elections commissioner", "elections commission", "election official", "polling booth",
    "high commissioner", "deputy high commissioner", "land reforms commission",
    "presidential commission", "bribery commission", "human rights commission",
    "police commission", "cabinet sub committee", "french embassy", "un high commissioner",
    "general election", "presidential election", "parliament election", "ballot paper",
    "sarath fonseka", "lrc director", "disappearances to begin hearings"
]

POSITIVE_GEM_PHRASES = [
    "hidden gem", "cultural gem", "architectural gem", "gem of a", "gem of an",
    "real gem", "absolute gem", "true gem", "gem of place", "gem in sri lanka"
]

SCAM_SIGNALS = [
    "scam", "scammed", "scamming", "fraud", "ripped off", "rip off", "ripoff",
    "overcharged", "tourist price", "double price", "fake guide", "pickpocket",
    "stolen", "robbed", "mugged", "harassed", "stalked", "groped", "assaulted",
    "refused meter", "meter tampered", "cheat", "cheated", "avoid", "warning",
    "unsafe", "dangerous", "threatened", "bribe", "extortion"
]

REAL_GEM_KEYWORDS = [
    "gem scam", "fake gem", "fake gems", "gem shop scam", "gem store scam",
    "overpriced gem", "ruby scam", "sapphire scam", "moonstone scam",
    "pushed into a gem shop", "forced into a gem shop", "fake jewel", "fake stones"
]

REAL_COMM_KEYWORDS = [
    "commission shop", "commission store", "driver commission", "shop commission",
    "took me to a shop", "took us to a shop", "driver took us to shop",
    "gets a commission", "paid a commission", "receive a commission",
    "spice garden scam", "forced to buy", "pushed to buy at shop"
]

REAL_TUKTUK_KEYWORDS = [
    "tuk tuk scam", "tuk-tuk scam", "tuktuk scam", "three wheeler scam",
    "tuk tuk overcharged", "tuk tuk driver lied", "tuk tuk driver cheat",
    "tuk tuk refused meter", "tuk tuk rip off"
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


def evaluate_record(title: str, content: str, is_scam: int, scam_type: str):
    text = f"{title or ''} {content or ''}".lower()

    # 1. Reject non-scam news
    if any(sig in text for sig in NON_SCAM_NEWS_SIGNALS):
        return 0, None

    # Strip negated scam phrases and neutral travel advice ("avoid crowds", "(not a scam)", etc.)
    clean_text_for_signals = text
    for phrase in (NEGATION_PHRASES + NEUTRAL_TRAVEL_PHRASES):
        clean_text_for_signals = clean_text_for_signals.replace(phrase, "")

    is_positive_gem = any(p in text for p in POSITIVE_GEM_PHRASES)
    has_scam_signal = any(re.search(r'\b' + re.escape(sig) + r'\b', clean_text_for_signals) for sig in SCAM_SIGNALS)

    has_real_gem = any(k in clean_text_for_signals for k in REAL_GEM_KEYWORDS)
    has_real_comm = any(k in clean_text_for_signals for k in REAL_COMM_KEYWORDS)
    has_real_tuktuk = any(k in clean_text_for_signals for k in REAL_TUKTUK_KEYWORDS)

    stype = str(scam_type or '').strip()

    if stype in ['gem_scam', 'Gem Scam', 'Gem & Jewelry Scam']:
        if has_real_gem:
            return 1, 'gem_scam'
        elif is_positive_gem or not has_scam_signal:
            return 0, None

    if stype in ['commission_shop', 'Commission Shop Trap']:
        if has_real_comm:
            return 1, 'commission_shop'
        else:
            return 0, None

    if stype in ['tuk_tuk_scam', 'Tuk-Tuk Overcharging', 'Tuk Tuk Scam']:
        fare_signals = [
            "overcharg", "fare", "meter", "no meter", "charged", "exorbitant", "extort",
            "demanded more", "price for ride", "driver lied", "driver scammed", "refused to turn on",
            "metered", "double price", "triple price", "rip off", "ripoff", "took long route",
            "detour to shop", "tuk tuk driver", "tuktuk driver", "trishaw driver", "overpriced tuk"
        ]
        has_fare_signal = any(sig in text for sig in fare_signals)
        if has_real_tuktuk or (("tuk tuk" in text or "tuktuk" in text or "three-wheeler" in text) and has_fare_signal):
            return 1, 'tuk_tuk_scam'
        elif any(k in text for k in ["free guide", "holy men", "panhandle", "donation", "snake-charmer", "shoe storage", "shoe keeper", "temple guide", "ticket office", "ticket gate", "grifter", "con", "hustling"]):
            return 1, 'fake_guide'
        elif any(k in text for k in ["commission", "spice garden", "herb garden", "tea factory"]):
            return 1, 'commission_shop'
        else:
            return (1 if is_scam else 0), None

    if is_scam == 1 and not has_scam_signal and not (has_real_gem or has_real_comm or has_real_tuktuk):
        return 0, None

    return (1 if is_scam else 0), (stype if (is_scam and stype) else None)


def clean_database():
    print("=" * 65)
    print(" Cleaning & Relabeling safety_heatmap.db ...")
    print("=" * 65)

    if not os.path.exists(DB_PATH):
        print(f"[ERROR] Database file not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT id, title, content, is_scam, scam_type, risk_level FROM reports")
    rows = c.fetchall()

    updates = []
    purged_count = 0
    retained_count = 0

    for r in rows:
        old_is_scam = int(r['is_scam'] or 0)
        old_stype = r['scam_type']
        new_is_scam, new_stype = evaluate_record(r['title'], r['content'], old_is_scam, old_stype)

        if old_is_scam == 1 and new_is_scam == 0:
            purged_count += 1
            updates.append((0, None, 1, r['id']))
        elif old_is_scam == 1 and new_is_scam == 1 and old_stype != new_stype:
            updates.append((1, new_stype, r['risk_level'] or 2, r['id']))
            retained_count += 1
        elif new_is_scam == 1:
            retained_count += 1

    print(f"Total reports analyzed: {len(rows):,}")
    print(f"Purged false-positive scams (set to SAFE): {purged_count:,}")
    print(f"Retained genuine scam reports:           {retained_count:,}")

    if updates:
        c.executemany("""
            UPDATE reports
            SET is_scam = ?, scam_type = ?, risk_level = ?
            WHERE id = ?
        """, [(u[0], u[1], u[2], u[3]) for u in updates])
        conn.commit()
        print("Successfully updated database records.")

    conn.close()


def clean_csv_files():
    print("\n" + "=" * 65)
    print(" Updating Master CSV Datasets ...")
    print("=" * 65)

    for csv_path in [PRIMARY_CSV_BACKEND, PRIMARY_CSV_ROOT]:
        if not os.path.exists(csv_path):
            continue

        df = pd.read_csv(csv_path, encoding="utf-8", low_memory=False)
        updated_rows = 0

        for idx, row in df.iterrows():
            text = str(row.get("text_content") or "")
            old_is_scam = int(row.get("is_scam") or 0)
            old_stype = str(row.get("scam_type") or "")
            new_is_scam, new_stype = evaluate_record("", text, old_is_scam, old_stype)

            if old_is_scam != new_is_scam or old_stype != (new_stype or ""):
                df.at[idx, "is_scam"] = new_is_scam
                df.at[idx, "scam_type"] = new_stype or ""
                df.at[idx, "risk_level"] = 2 if new_is_scam == 1 else 1
                updated_rows += 1

        df.to_csv(csv_path, index=False, encoding="utf-8")
        print(f"Updated {csv_path}: {updated_rows:,} rows relabeled.")


if __name__ == "__main__":
    clean_database()
    clean_csv_files()
