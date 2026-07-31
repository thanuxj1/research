"""
Coverage Gap Analysis — Table 2 for Thesis Methodology
IT22629180

Fuzzy-matches canonical_destinations.csv against safety_heatmap.db
to compute per-destination coverage rates and identify gaps.

Output: Gap table ranked by priority x record count.
"""
import os
import csv
import sqlite3
from difflib import SequenceMatcher


def fuzzy_match(needle: str, haystack: list, threshold: float = 0.55):
    """Return (best_match_name, score, record_count) or None."""
    needle_lower = needle.lower().strip()
    best_match = None
    best_score = 0
    best_count = 0

    for db_name, count in haystack:
        db_lower = db_name.lower().strip()

        # Exact substring check first (fast path)
        if needle_lower in db_lower or db_lower in needle_lower:
            if count > best_count or (count == best_count and len(db_lower) > len(best_match or "")):
                best_match = db_name
                best_score = 1.0
                best_count = count

        # Fuzzy ratio
        ratio = SequenceMatcher(None, needle_lower, db_lower).ratio()
        if ratio > best_score:
            best_match = db_name
            best_score = ratio
            best_count = count

    if best_score >= threshold:
        return best_match, best_score, best_count
    return None


def run_gap_analysis():
    base_dir = os.path.dirname(__file__)
    csv_path = os.path.join(base_dir, "canonical_destinations.csv")
    db_path = os.path.join(base_dir, "safety_heatmap.db")

    # Load canonical destinations
    canonical = []
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            names = [row["destination_name"].strip()]
            if row.get("alt_names"):
                names.extend([n.strip() for n in row["alt_names"].split(";")])
            canonical.append({
                "destination": row["destination_name"].strip(),
                "alt_names": names,
                "province": row["province"].strip(),
                "category": row["category"].strip(),
                "unesco": row.get("unesco_or_tier0_listed", "No").strip(),
                "priority": row["priority"].strip(),
            })

    # Load DB location names with counts
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT location_name, COUNT(*) as cnt
        FROM reports
        WHERE location_name IS NOT NULL AND location_name != ''
        GROUP BY location_name
    """)
    db_locations = cur.fetchall()  # [(name, count), ...]

    # Also get total stats
    cur.execute("SELECT COUNT(*) FROM reports")
    total_records = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT location_name) FROM reports WHERE location_name IS NOT NULL")
    total_unique = cur.fetchone()[0]
    conn.close()

    print("=" * 80)
    print("  COVERAGE GAP ANALYSIS — Canonical Destination Registry vs Database")
    print(f"  Database: {total_records} records | {total_unique} unique locations")
    print(f"  Canonical List: {len(canonical)} destinations")
    print("=" * 80)

    covered = []
    gaps = []
    province_stats = {}

    for dest in canonical:
        best_result = None

        # Try each name variant (main name + alt names)
        for name in dest["alt_names"]:
            result = fuzzy_match(name, db_locations)
            if result:
                match_name, score, count = result
                if best_result is None or count > best_result[2]:
                    best_result = (match_name, score, count)

        prov = dest["province"]
        if prov not in province_stats:
            province_stats[prov] = {"total": 0, "covered": 0, "gap": 0}
        province_stats[prov]["total"] += 1

        if best_result and best_result[2] > 0:
            covered.append({
                **dest,
                "db_match": best_result[0],
                "match_score": best_result[1],
                "record_count": best_result[2],
            })
            province_stats[prov]["covered"] += 1
        else:
            gaps.append(dest)
            province_stats[prov]["gap"] += 1

    # Sort gaps: High priority first, then Medium, then Low
    priority_order = {"High": 0, "Medium": 1, "Low": 2}
    gaps.sort(key=lambda x: priority_order.get(x["priority"], 3))
    covered.sort(key=lambda x: -x["record_count"])

    # Print results
    coverage_rate = len(covered) / len(canonical) * 100 if canonical else 0

    print(f"\n{'='*80}")
    print(f"  OVERALL COVERAGE: {len(covered)}/{len(canonical)} ({coverage_rate:.1f}%)")
    print(f"{'='*80}")

    print(f"\n--- PROVINCE BREAKDOWN ---")
    print(f"{'Province':<25} {'Total':>6} {'Covered':>8} {'Gap':>5} {'Rate':>8}")
    print("-" * 55)
    for prov, stats in sorted(province_stats.items()):
        rate = stats["covered"] / stats["total"] * 100 if stats["total"] else 0
        flag = " *** LOW" if rate < 50 else ""
        print(f"{prov:<25} {stats['total']:>6} {stats['covered']:>8} {stats['gap']:>5} {rate:>7.1f}%{flag}")

    print(f"\n--- GAPS ({len(gaps)} destinations missing) ---")
    print(f"{'Priority':<8} {'Destination':<40} {'Province':<20} {'Category'}")
    print("-" * 90)
    for g in gaps:
        marker = "***" if g["priority"] == "High" else "  "
        print(f"{marker}{g['priority']:<6} {g['destination']:<40} {g['province']:<20} {g['category']}")

    high_gaps = [g for g in gaps if g["priority"] == "High"]
    print(f"\n--- CRITICAL HIGH-PRIORITY GAPS: {len(high_gaps)} ---")
    for g in high_gaps:
        print(f"  !!! {g['destination']} ({g['province']}) — {g['category']}")

    print(f"\n--- COVERED DESTINATIONS (Top 30 by record count) ---")
    print(f"{'Records':>8} {'Destination':<40} {'DB Match':<50}")
    print("-" * 100)
    for c in covered[:30]:
        print(f"{c['record_count']:>8} {c['destination']:<40} {c['db_match']:<50}")

    # Generate gap queries for Google Maps scraping
    print(f"\n--- GOOGLE MAPS QUERIES FOR GAP FILLING ---")
    gap_queries = []
    for g in gaps:
        query = f"{g['destination']} Sri Lanka tourist reviews"
        gap_queries.append(query)
        print(f'  "{query}",')

    # Save gap report to file
    report_path = os.path.join(base_dir, "coverage_gap_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"COVERAGE GAP ANALYSIS REPORT\n")
        f.write(f"Generated: {__import__('datetime').datetime.now().isoformat()}\n")
        f.write(f"Database: {total_records} records, {total_unique} unique locations\n")
        f.write(f"Canonical: {len(canonical)} destinations\n")
        f.write(f"Coverage: {len(covered)}/{len(canonical)} ({coverage_rate:.1f}%)\n\n")
        f.write(f"GAPS ({len(gaps)}):\n")
        for g in gaps:
            f.write(f"  [{g['priority']}] {g['destination']} ({g['province']}) - {g['category']}\n")
        f.write(f"\nCOVERED ({len(covered)}):\n")
        for c in covered:
            f.write(f"  [{c['record_count']} records] {c['destination']} -> {c['db_match']}\n")

    print(f"\n[Saved] Full report: {report_path}")

    return gaps, covered, gap_queries


if __name__ == "__main__":
    gaps, covered, queries = run_gap_analysis()
