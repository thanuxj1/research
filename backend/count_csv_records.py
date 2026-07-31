
import re
import os

def count_records():
    csv_path = "training/dataset/sample_data.csv"
    if not os.path.exists(csv_path):
        print("CSV not found.")
        return

    with open(csv_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    # Pattern: , [01] , [scam_type] , [sentiment] \n
    # This pattern identifies the end of a record.
    pattern = re.compile(r',[01],[^,]*,(-?\d+\.?\d*)\s*(\n|$)')
    matches = pattern.findall(content)
    print(f"Total records found via end-pattern: {len(matches)}")

    # Let's also check for lines starting with quotes
    lines = content.splitlines()
    quoted_starts = sum(1 for line in lines if line.startswith('"'))
    print(f"Lines starting with double-quote: {quoted_starts}")
    
    # Check for records that are not quoted but are single-line
    # These would have ,0, or ,1, in them and NOT start with "
    single_line_unquoted = sum(1 for line in lines if not line.startswith('"') and re.search(r',[01],', line))
    print(f"Unquoted lines with [01] pattern: {single_line_unquoted}")

if __name__ == "__main__":
    count_records()
