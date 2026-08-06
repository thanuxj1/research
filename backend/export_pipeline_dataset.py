"""
Export Pipeline Database to Research Dataset
IT22629180

Exports all ingested safety reports from the SQLite database to:
  1. safety_incidents_dataset.csv     — full flat dataset for ML / research
  2. safety_incidents_dataset.jsonl   — JSON Lines (one record per line, for LLM fine-tuning)
  3. dataset_stats.json               — statistics summary for documentation

Output columns / fields:
  id, source, source_label, source_weight, credibility_tier,
  title, content, content_word_count,
  is_scam, scam_type, risk_level, risk_label,
  sentiment_score, location_name, district,
  latitude, longitude, url, helpful_votes,
  demographic_target, created_at, data_quality_flag
"""

import sys
import os
import csv
import json
import re
import sqlite3
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "safety_heatmap.db")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dataset_exports")
os.makedirs(OUT_DIR, exist_ok=True)

CSV_PATH   = os.path.join(OUT_DIR, "safety_incidents_dataset.csv")
JSONL_PATH = os.path.join(OUT_DIR, "safety_incidents_dataset.jsonl")
STATS_PATH = os.path.join(OUT_DIR, "dataset_stats.json")

# ── Source metadata ─────────────────────────────────────────────────────────────

SOURCE_META = {
    "tripadvisor_csv":  {"label": "TripAdvisor Reviews",         "tier": "Tier-2 Community",   "weight": 0.55},
    "dataset_csv":      {"label": "Curated Safety Dataset (CSV)", "tier": "Tier-1 Curated",     "weight": 0.70},
    "youtube":          {"label": "YouTube Safety Videos",        "tier": "Tier-2 Community",   "weight": 0.50},
    "google_news":      {"label": "Google News RSS",              "tier": "Tier-2 Aggregator",  "weight": 0.55},
    "sunday_times":     {"label": "Sunday Times (LK)",            "tier": "Tier-1 Press",       "weight": 0.75},
    "newswire":         {"label": "Newswire.lk",                  "tier": "Tier-1 Press",       "weight": 0.63},
    "newswire_lk":      {"label": "Newswire.lk",                  "tier": "Tier-1 Press",       "weight": 0.63},
    "daily_mirror":     {"label": "Daily Mirror (LK)",            "tier": "Tier-1 Press",       "weight": 0.72},
    "newsfirst":        {"label": "NewsFirst / Sirasa",           "tier": "Tier-1 Press",       "weight": 0.65},
    "reddit":           {"label": "Reddit (r/srilanka etc.)",     "tier": "Tier-2 Community",   "weight": 0.45},
    "web":              {"label": "Web Scrape",                   "tier": "Tier-3 Web",         "weight": 0.35},
    "news":             {"label": "News (generic)",               "tier": "Tier-2 Aggregator",  "weight": 0.50},
}

RISK_LABELS = {0: "Unknown", 1: "Low", 2: "Moderate", 3: "High"}

SCAM_CATEGORY_MAP = {
    "gem scam":                 "Gem / Jewellery Scam",
    "gem shop":                 "Gem / Jewellery Scam",
    "tuk tuk scam":             "Tuk-Tuk / Transport Scam",
    "tuk-tuk scam":             "Tuk-Tuk / Transport Scam",
    "transport fraud":          "Tuk-Tuk / Transport Scam",
    "fake guide":               "Fake Guide / Monk",
    "overcharging":             "Overcharging",
    "theft / robbery":          "Theft / Robbery",
    "harassment / assault":     "Harassment / Assault",
    "harassment":               "Harassment / Assault",
    "food / drink spiking":     "Food / Drink Spiking",
    "tourist safety incident":  "General Safety Incident",
    "tourist scam / warning":   "General Safety Incident",
    "safety advisory":          "Safety Advisory (Non-Incident)",
    "travel advisory":          "Safety Advisory (Non-Incident)",
    "general safety":           "Safety Advisory (Non-Incident)",
    "general scam":             "General Safety Incident",
}


def normalise_scam_type(raw: str) -> str:
    if not raw:
        return "General Safety Incident"
    key = raw.strip().lower()
    for pattern, normalised in SCAM_CATEGORY_MAP.items():
        if pattern in key:
            return normalised
    return raw.strip()


def word_count(text: str) -> int:
    return len(re.findall(r"\w+", text or ""))


def data_quality_flag(row: dict) -> str:
    """
    Returns a quality flag string:
      HIGH   — has URL, full body (>150 words), lat/lon, is_scam classified
      MEDIUM — has URL or good content but missing some fields
      LOW    — minimal content or no URL or no coordinates
    """
    has_url     = bool(row.get("url"))
    has_coords  = row.get("latitude") is not None and row.get("longitude") is not None
    word_ct     = row.get("content_word_count", 0)
    has_type    = bool(row.get("scam_type")) and row.get("scam_type") not in ("General Safety Incident", "General Scam")

    score = sum([
        has_url,
        has_coords,
        word_ct >= 80,
        word_ct >= 200,
        has_type,
    ])

    if score >= 4:
        return "HIGH"
    elif score >= 2:
        return "MEDIUM"
    return "LOW"


# ── SL district inference from lat/lon ─────────────────────────────────────────

DISTRICT_BOUNDS = {
    "Colombo":     (6.75, 79.80, 7.00, 80.00),
    "Gampaha":     (7.00, 79.85, 7.25, 80.20),
    "Kalutara":    (6.40, 79.85, 6.75, 80.30),
    "Kandy":       (7.10, 80.45, 7.50, 81.00),
    "Matale":      (7.40, 80.40, 8.00, 80.85),
    "Nuwara Eliya":(6.70, 80.55, 7.10, 81.10),
    "Galle":       (5.85, 79.95, 6.30, 80.55),
    "Matara":      (5.80, 80.40, 6.10, 81.00),
    "Hambantota":  (5.95, 80.90, 6.35, 81.40),
    "Jaffna":      (9.40, 79.80, 9.85, 80.45),
    "Kilinochchi": (8.95, 80.15, 9.40, 80.55),
    "Mannar":      (8.55, 79.85, 9.15, 80.30),
    "Vavuniya":    (8.55, 80.30, 9.00, 80.75),
    "Mullaitivu":  (8.85, 80.50, 9.50, 81.20),
    "Batticaloa":  (7.50, 81.45, 8.40, 81.95),
    "Ampara":      (6.95, 81.30, 7.60, 82.00),
    "Trincomalee": (8.30, 81.00, 9.00, 81.70),
    "Kurunegala":  (7.35, 79.95, 7.90, 80.60),
    "Puttalam":    (7.65, 79.70, 8.25, 80.15),
    "Anuradhapura":(8.15, 80.15, 8.90, 80.80),
    "Polonnaruwa": (7.75, 80.80, 8.35, 81.30),
    "Badulla":     (6.75, 80.90, 7.40, 81.55),
    "Monaragala":  (6.50, 81.00, 7.10, 81.90),
    "Ratnapura":   (6.25, 80.30, 6.80, 80.95),
    "Kegalle":     (6.95, 80.25, 7.35, 80.65),
}


def infer_district(lat, lon) -> str:
    if lat is None or lon is None:
        return ""
    for dist, (min_lat, min_lon, max_lat, max_lon) in DISTRICT_BOUNDS.items():
        if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
            return dist
    return "Sri Lanka"


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN EXPORT
# ══════════════════════════════════════════════════════════════════════════════

CSV_COLUMNS = [
    "id",
    "source",
    "source_label",
    "source_weight",
    "credibility_tier",
    "title",
    "content",
    "content_word_count",
    "is_scam",
    "scam_type",
    "scam_type_normalised",
    "risk_level",
    "risk_label",
    "sentiment_score",
    "location_name",
    "district",
    "latitude",
    "longitude",
    "url",
    "helpful_votes",
    "demographic_target",
    "created_at",
    "data_quality_flag",
]


def build_record(row: dict) -> dict:
    source     = row.get("source") or "unknown"
    meta       = SOURCE_META.get(source, {"label": source, "tier": "Unknown", "weight": 0.35})
    content    = (row.get("content") or "").strip()
    wc         = word_count(content)
    lat        = row.get("latitude")
    lon        = row.get("longitude")
    district   = row.get("district") or infer_district(lat, lon)
    scam_raw   = row.get("scam_type") or ""
    is_scam    = bool(row.get("is_scam"))
    risk_lv    = int(row.get("risk_level") or 1)
    sent       = row.get("sentiment_score")
    url        = (row.get("url") or "").strip()
    helpful    = row.get("helpful_votes") or 0
    demo       = row.get("demographic_target") or "Tourists"
    created    = row.get("created_at") or ""

    rec = {
        "id":                  row["id"],
        "source":              source,
        "source_label":        meta["label"],
        "source_weight":       meta["weight"],
        "credibility_tier":    meta["tier"],
        "title":               (row.get("title") or "").strip(),
        "content":             content,
        "content_word_count":  wc,
        "is_scam":             int(is_scam),
        "scam_type":           scam_raw,
        "scam_type_normalised": normalise_scam_type(scam_raw),
        "risk_level":          risk_lv,
        "risk_label":          RISK_LABELS.get(risk_lv, "Unknown"),
        "sentiment_score":     round(float(sent), 4) if sent is not None else None,
        "location_name":       (row.get("location_name") or "Sri Lanka").strip(),
        "district":            district,
        "latitude":            round(float(lat), 6) if lat is not None else None,
        "longitude":           round(float(lon), 6) if lon is not None else None,
        "url":                 url,
        "helpful_votes":       int(helpful) if helpful else 0,
        "demographic_target":  demo,
        "created_at":          created,
    }
    rec["data_quality_flag"] = data_quality_flag(rec)
    return rec


def main():
    print("=" * 64)
    print("  SafeTravel LK — Pipeline Dataset Exporter")
    print("=" * 64)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM reports ORDER BY id ASC")
    rows = cur.fetchall()
    conn.close()

    print(f"\n  Total records in DB: {len(rows)}")

    records = [build_record(dict(r)) for r in rows]

    # ── 1. CSV export ──────────────────────────────────────────────────────────
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    print(f"\n  ✅ CSV:   {CSV_PATH}")
    print(f"      {len(records)} rows × {len(CSV_COLUMNS)} columns")

    # ── 2. JSONL export ────────────────────────────────────────────────────────
    with open(JSONL_PATH, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"\n  ✅ JSONL: {JSONL_PATH}")
    print(f"      {len(records)} lines (one JSON object per line)")

    # ── 3. Stats export ────────────────────────────────────────────────────────
    from collections import Counter

    source_counts   = Counter(r["source"]              for r in records)
    scam_type_counts= Counter(r["scam_type_normalised"] for r in records)
    district_counts = Counter(r["district"]             for r in records if r["district"])
    quality_counts  = Counter(r["data_quality_flag"]    for r in records)
    tier_counts     = Counter(r["credibility_tier"]     for r in records)

    scam_total   = sum(1 for r in records if r["is_scam"])
    advis_total  = sum(1 for r in records if not r["is_scam"])
    has_url      = sum(1 for r in records if r["url"])
    has_coords   = sum(1 for r in records if r["latitude"] is not None)
    avg_words    = sum(r["content_word_count"] for r in records) / len(records) if records else 0

    stats = {
        "exported_at":          datetime.now(timezone.utc).isoformat(),
        "total_records":        len(records),
        "scam_reports":         scam_total,
        "advisory_reports":     advis_total,
        "records_with_url":     has_url,
        "records_with_coords":  has_coords,
        "avg_content_words":    round(avg_words, 1),
        "by_source":            dict(source_counts.most_common()),
        "by_credibility_tier":  dict(tier_counts.most_common()),
        "by_scam_type":         dict(scam_type_counts.most_common()),
        "by_district":          dict(district_counts.most_common()),
        "by_data_quality":      dict(quality_counts.most_common()),
        "csv_path":             CSV_PATH,
        "jsonl_path":           JSONL_PATH,
    }

    with open(STATS_PATH, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    print(f"\n  ✅ Stats: {STATS_PATH}")

    # ── Print summary ──────────────────────────────────────────────────────────
    print("\n" + "─" * 64)
    print("  DATASET SUMMARY")
    print("─" * 64)
    print(f"  Total records       : {len(records)}")
    print(f"  Confirmed scams     : {scam_total}")
    print(f"  Safety advisories   : {advis_total}")
    print(f"  Records with URL    : {has_url} ({has_url*100//len(records)}%)")
    print(f"  Records with coords : {has_coords} ({has_coords*100//len(records)}%)")
    print(f"  Avg content length  : {avg_words:.0f} words")

    print("\n  Records by source:")
    for src, cnt in source_counts.most_common():
        label = SOURCE_META.get(src, {}).get("label", src)
        print(f"    {label:<35} {cnt:>4}")

    print("\n  Records by scam type:")
    for st, cnt in scam_type_counts.most_common():
        print(f"    {st:<40} {cnt:>4}")

    print("\n  Records by district:")
    for d, cnt in district_counts.most_common(10):
        print(f"    {d:<30} {cnt:>4}")

    print("\n  Data quality breakdown:")
    for q, cnt in quality_counts.most_common():
        print(f"    {q:<10} {cnt:>4}")

    print("\n" + "=" * 64)
    print("  Export complete.")
    print(f"  Files saved to: {os.path.abspath(OUT_DIR)}")
    print("=" * 64)


if __name__ == "__main__":
    main()
