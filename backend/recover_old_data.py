
import os
import sys
import re

# Add parent directory to path to import app/data_pipeline
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.db.models import Report
from data_pipeline.strict_filter import passes_strict_filter
from fix_data_quality import extract_location_expanded, detect_scam_type_expanded, EXPANDED_LOCATIONS

def recover_data():
    csv_path = "training/dataset/sample_data.csv"
    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found.")
        return

    with open(csv_path, 'r', encoding='utf-8', errors='replace') as f:
        content_all = f.read()

    # The separator is ,(0|1),(scam_type),(sentiment)\n
    # We use finditer to get all matches of the "tail" of a record
    tail_regex = re.compile(r',([01]),([^,]*),(-?\d+\.?\d*)\s*(\n|$)')
    
    records = []
    last_end = 0
    # Skip header
    header_end = content_all.find('\n') + 1
    last_end = header_end

    for match in tail_regex.finditer(content_all, last_end):
        is_scam_str = match.group(1)
        scam_type = match.group(2)
        sentiment_str = match.group(3)
        
        # Everything from last_end to the start of this match is the 'text'
        text = content_all[last_end:match.start()].strip()
        
        # Update last_end for next record
        last_end = match.end()
        
        if text:
            # Clean text (remove leading/trailing quotes if they exist)
            if text.startswith('"') and text.endswith('"'):
                text = text[1:-1]
            records.append((text, is_scam_str, scam_type, sentiment_str))

    print(f"Found {len(records)} records in CSV.")

    db = SessionLocal()
    added = 0
    skipped_filter = 0
    skipped_dup = 0
    
    seen_content = set()

    for text, is_scam_str, scam_type, sentiment_str in records:
        if not text or len(text) < 10:
            continue

        # Filter
        if not passes_strict_filter("", text):
            skipped_filter += 1
            continue

        # De-dupe
        if text in seen_content:
            skipped_dup += 1
            continue
        seen_content.add(text)

        if db.query(Report).filter(Report.content == text).first():
            skipped_dup += 1
            continue

        is_scam = is_scam_str == '1'
        try:
            sentiment = float(sentiment_str)
        except:
            sentiment = 0.0

        # Location
        lat, lon, loc_name = extract_location_expanded(text)
        if not lat or not lon:
            lat, lon = EXPANDED_LOCATIONS["sri lanka"]
            loc_name = "Sri Lanka"

        report = Report(
            source="legacy_recovery",
            url=None,
            title=scam_type.replace('_', ' ').title() if scam_type else "Safety Report",
            content=text,
            latitude=lat,
            longitude=lon,
            location_name=loc_name,
            is_scam=is_scam,
            scam_type=scam_type or detect_scam_type_expanded(text),
            sentiment_score=sentiment,
            risk_level=2 if is_scam else 1
        )
        db.add(report)
        added += 1
        
        if added % 500 == 0:
            db.commit()
            print(f"  Added {added} records...")

    db.commit()
    print(f"\nFINISH!")
    print(f"  Successfully Added:      {added}")
    print(f"  Skipped (Strict Filter): {skipped_filter}")
    print(f"  Skipped (Duplicate):     {skipped_dup}")
    db.close()

if __name__ == "__main__":
    recover_data()
