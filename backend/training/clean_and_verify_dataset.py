"""
Data Cleaning & Verification Pipeline — SafeTravel LK
IT22629180

Cleans, deduplicates, validates, and audits primary_master_dataset.csv:
  1. HTML entity unescaping and unicode character cleaning
  2. Deduplication on text_content
  3. Short text / noise removal (text len < 15 chars)
  4. Sri Lanka coordinate boundary validation (Lat: 5.8-9.9, Lon: 79.5-82.0)
  5. Label integrity and range checks (sentiment, risk_level, is_scam)
  6. Audit report generation
"""
import os
import sys
import html
import re
import pandas as pd
import numpy as np

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESEARCH_DIR = os.path.dirname(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)

INPUT_CSV = os.path.join(RESEARCH_DIR, "primary_master_dataset.csv")
OUTPUT_CLEAN_CSV = os.path.join(RESEARCH_DIR, "primary_master_dataset_clean.csv")
OUTPUT_BACKEND_CSV = os.path.join(BACKEND_DIR, "training", "dataset", "primary_master_dataset_clean.csv")
VERIFY_REPORT_TXT = os.path.join(RESEARCH_DIR, "dataset_verification_report.txt")

# Sri Lanka Bounding Box
SL_LAT_MIN, SL_LAT_MAX = 5.8, 9.9
SL_LON_MIN, SL_LON_MAX = 79.5, 82.0


def clean_text_string(text):
    if not isinstance(text, str) or not text.strip():
        return ""
    # Unescape HTML
    txt = html.unescape(text)
    # Remove control characters / non-printable unicode artifacts
    txt = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', txt)
    # Normalize extra spaces
    txt = re.sub(r'\s+', ' ', txt).strip()
    return txt


def clean_and_verify():
    print("=" * 65)
    print("  Data Cleaning & Quality Verification — SafeTravel LK")
    print("  IT22629180")
    print("=" * 65)

    if not os.path.exists(INPUT_CSV):
        print(f"[ERROR] Input dataset not found: {INPUT_CSV}")
        return

    print(f"\n[1/5] Loading primary dataset: {INPUT_CSV}")
    df = pd.read_csv(INPUT_CSV, encoding="utf-8", low_memory=False)
    raw_count = len(df)
    print(f"      -> Loaded {raw_count:,} raw records.")

    # 1. Text Cleaning
    print("\n[2/5] Cleaning text & removing noise...")
    df["text_content"] = df["text_content"].astype(str).apply(clean_text_string)

    # Filter out empty or very short texts (< 15 chars)
    df["text_len"] = df["text_content"].str.len()
    short_dropped = len(df[df["text_len"] < 15])
    df = df[df["text_len"] >= 15].copy()

    # 2. Deduplication
    print("\n[3/5] Deduplicating records...")
    dup_count = df.duplicated(subset=["text_content"]).sum()
    df = df.drop_duplicates(subset=["text_content"]).reset_index(drop=True)

    # 3. Coordinate validation (Sri Lanka bounding box)
    print("\n[4/5] Validating coordinates and value ranges...")
    valid_coords_mask = (
        (df["lat"] >= SL_LAT_MIN) & (df["lat"] <= SL_LAT_MAX) &
        (df["lon"] >= SL_LON_MIN) & (df["lon"] <= SL_LON_MAX)
    )
    invalid_coords_count = len(df[df["lat"].notnull() & ~valid_coords_mask])
    # Invalidate out-of-bound coords
    df.loc[df["lat"].notnull() & ~valid_coords_mask, ["lat", "lon"]] = np.nan

    # Validate ranges
    df["sentiment"] = df["sentiment"].clip(-1.0, 1.0)
    df["risk_level"] = df["risk_level"].clip(1, 3)
    df["is_scam"] = df["is_scam"].apply(lambda x: 1 if x == 1 else 0)

    # Drop temporary column
    df = df.drop(columns=["text_len"])

    final_count = len(df)
    print(f"      -> Cleaned records: {final_count:,} (Removed {raw_count - final_count:,} noise/duplicate rows)")

    # 4. Save Cleaned Datasets
    print("\n[5/5] Saving cleaned master dataset...")
    df.to_csv(OUTPUT_CLEAN_CSV, index=False, encoding="utf-8")
    df.to_csv(OUTPUT_BACKEND_CSV, index=False, encoding="utf-8")

    # 5. Verification Report Generation
    report_lines = []
    report_lines.append("=================================================================")
    report_lines.append("          SAFETRAVEL LK — DATASET VERIFICATION REPORT           ")
    report_lines.append("=================================================================")
    report_lines.append(f"Initial Raw Records:      {raw_count:,}")
    report_lines.append(f"Short / Noise Removed:    {short_dropped:,}")
    report_lines.append(f"Duplicates Removed:       {dup_count:,}")
    report_lines.append(f"Invalid Coords Cleared:   {invalid_coords_count:,}")
    report_lines.append(f"Final Cleaned Records:    {final_count:,}")
    report_lines.append("-----------------------------------------------------------------")
    report_lines.append("CLASS BALANCE & DATA DISTRIBUTION:")
    scam_count = (df['is_scam'] == 1).sum()
    safe_count = (df['is_scam'] == 0).sum()
    report_lines.append(f"  - Scam / Incident (1):  {scam_count:,} ({scam_count/final_count:.1%})")
    report_lines.append(f"  - Safe / General (0):   {safe_count:,} ({safe_count/final_count:.1%})")
    report_lines.append("-----------------------------------------------------------------")
    report_lines.append("CATEGORY BREAKDOWN:")
    for cat, cnt in df['data_category'].value_counts().items():
        report_lines.append(f"  - {cat.upper()}: {cnt:,} ({cnt/final_count:.1%})")
    report_lines.append("-----------------------------------------------------------------")
    report_lines.append("DATASET SOURCES BREAKDOWN:")
    for src, cnt in df['dataset_source'].value_counts().items():
        report_lines.append(f"  - {src}: {cnt:,}")
    report_lines.append("-----------------------------------------------------------------")
    report_lines.append("GEOLOCATION METRICS:")
    geocoded_cnt = df['lat'].notnull().sum()
    report_lines.append(f"  - Valid SL Geocoded:   {geocoded_cnt:,} ({geocoded_cnt/final_count:.1%})")
    report_lines.append("=================================================================")

    report_text = "\n".join(report_lines)
    print(f"\n{report_text}\n")

    with open(VERIFY_REPORT_TXT, "w", encoding="utf-8") as f:
        f.write(report_text)

    print(f" Verification report saved to: {VERIFY_REPORT_TXT}")
    print(f" Clean dataset saved to: {OUTPUT_CLEAN_CSV}")
    print("=" * 65)


if __name__ == "__main__":
    clean_and_verify()
