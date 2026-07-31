
import os
import sys
import re

# Add parent directory to path to import app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.db.models import Report

def update_legacy_sources():
    db = SessionLocal()
    try:
        # We only update reports from 'legacy_recovery'
        reports = db.query(Report).filter(Report.source == 'legacy_recovery').all()
        print(f"Found {len(reports)} legacy records to update.")

        updated_count = 0
        
        source_keywords = {
            'facebook': 'facebook (recovered)',
            'instagram': 'instagram (recovered)',
            'youtube': 'youtube (recovered)',
            'tripadvisor': 'tripadvisor (recovered)',
            'lonely planet': 'lonelyplanet (recovered)',
            'reddit': 'reddit (recovered)',
            'pickme': 'mobile_app (recovered)',
            'uber': 'mobile_app (recovered)',
            'booking.com': 'online_booking (recovered)',
            'airbnb': 'online_booking (recovered)',
            'agoda': 'online_booking (recovered)',
            'news': 'news (recovered)',
            'daily mirror': 'news (recovered)',
            'ada derana': 'news (recovered)',
            'colombo gazette': 'news (recovered)',
            'sunday times': 'news (recovered)',
        }

        for report in reports:
            content_lower = report.content.lower()
            new_source = None
            
            # 1. Try to find a specific keyword
            for kw, src in source_keywords.items():
                if kw in content_lower:
                    new_source = src
                    break
            
            # 2. If no keyword, default to 'travel_forum (recovered)'
            if not new_source:
                new_source = 'travel_forum (recovered)'
            
            # 3. Try to extract a URL if one is embedded in text (legacy data sometimes has them)
            url_match = re.search(r'https?://[^\s<>"]+|www\.[^\s<>"]+', report.content)
            if url_match and not report.url:
                report.url = url_match.group(0)
            
            report.source = new_source
            updated_count += 1
            
        db.commit()
        print(f"Successfully updated {updated_count} legacy records with descriptive source names.")
        
    except Exception as e:
        db.rollback()
        print(f"Error updating legacy sources: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    update_legacy_sources()
