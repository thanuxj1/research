
import os
import sys
import re

# Add parent directory to path to import app/data_pipeline
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from data_pipeline.strict_filter import passes_strict_filter, HARD_EXCLUSIONS, NEGATIVE_SIGNALS, TOURIST_CONTEXT

def analyze_csv_skips():
    csv_path = "training/dataset/sample_data.csv"
    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found.")
        return

    with open(csv_path, 'r', encoding='utf-8', errors='replace') as f:
        content_all = f.read()

    tail_regex = re.compile(r',([01]),([^,]*),(-?\d+\.?\d*)\s*(\n|$)')
    
    total = 0
    passed = 0
    fail_exclusion = 0
    fail_geo = 0
    fail_tourist = 0
    fail_negative = 0
    
    last_end = content_all.find('\n') + 1

    for match in tail_regex.finditer(content_all, last_end):
        total += 1
        text = content_all[last_end:match.start()].strip().lower()
        last_end = match.end()
        
        # Breakdown of passes_strict_filter
        # 1. Hard exclusion
        if any(excl in text for excl in HARD_EXCLUSIONS):
            fail_exclusion += 1
            continue
            
        # 2. Geographic Gate
        lanka_terms = ["sri lanka", "lankan", "lanka", "colombo", "kandy", "galle", "ella", "sigiriya", "negombo", "mirissa", "hikkaduwa", "unawatuna", "nuwara eliya", "arugam", "bentota", "jaffna", "dambulla", "polonnaruwa", "trincomalee"]
        if not any(term in text for term in lanka_terms):
            fail_geo += 1
            continue
            
        # 3. Tourism Context
        strong_tourist = ["tourist", "tourists", "tourism", "traveler", "traveller", "traveling", "travelling", "travel to", "backpacker", "backpacking", "solo travel", "solo trip", "vacation", "holiday", "trip to sri lanka", "trip to colombo", "visited sri lanka", "visiting sri lanka"]
        infrastructure = ["hostel", "guesthouse", "hotel in", "stayed at", "tuk tuk", "tuk-tuk", "three-wheeler", "safari", "tour guide", "tour operator", "sightseeing", "itinerary", "day trip", "cultural triangle"]
        locations = ["colombo", "sigiriya", "kandy", "ella", "galle fort", "mirissa", "arugam", "negombo", "hikkaduwa", "unawatuna", "nuwara eliya"]
        
        has_strong = any(kw in text for kw in strong_tourist)
        has_infra = any(kw in text for kw in infrastructure)
        has_location = any(kw in text for kw in locations)
        
        if not (has_strong or (has_infra and has_location)):
            fail_tourist += 1
            continue
            
        # 4. Negative Signal
        if not any(sig in text for sig in NEGATIVE_SIGNALS):
            fail_negative += 1
            continue
            
        passed += 1

    print(f"Analysis of {total} records:")
    print(f"  Passed:                {passed}")
    print(f"  Failed (Exclusion):    {fail_exclusion}")
    print(f"  Failed (Geo Gate):     {fail_geo}")
    print(f"  Failed (Tourist Ctx):  {fail_tourist}")
    print(f"  Failed (Negative Sig): {fail_negative}")

if __name__ == "__main__":
    analyze_csv_skips()
