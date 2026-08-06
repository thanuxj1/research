"""
SLTDA / Tourist Police PDF Ingester — SafeTravel LK Research Engine
IT22629180

PURPOSE:
  Extracts structured safety incident records from official Sri Lanka government
  and tourism authority PDFs. These are Tier-0 / Tier-1 sources with the highest
  credibility weights in the system (0.97–1.00), so even 20–30 records from
  these sources significantly improves the dataset's credibility tier distribution.

SUPPORTED PDF TYPES:
  1. SLTDA Annual Statistical Reports (tourism statistics, complaint summaries)
     — Source: sltda.gov.lk/statistics
     — Weight: 0.97

  2. Sri Lanka Tourist Police Annual Reports / Press Releases
     — Source: tourist.police.lk or embedded in SLTDA reports
     — Weight: 0.97

  3. Ministry of Tourism Progress Reports
     — Weight: 0.92

  4. Ad-hoc: Any PDF you pass via --pdf argument (manual mode)

HOW TO USE:
  # Auto-download and ingest all known SLTDA PDFs:
      python -m data_pipeline.ingest_sltda_pdf --auto

  # Ingest a specific local PDF you already have:
      python -m data_pipeline.ingest_sltda_pdf --pdf /path/to/sltda_report_2023.pdf

  # Ingest a PDF from a URL:
      python -m data_pipeline.ingest_sltda_pdf --url https://sltda.gov.lk/reports/annual2023.pdf

  # Dry run (print extracted records, do not write to DB):
      python -m data_pipeline.ingest_sltda_pdf --auto --dry-run

  # Show all extracted text (debug mode):
      python -m data_pipeline.ingest_sltda_pdf --pdf report.pdf --debug

DEPENDENCIES:
  pip install pdfplumber requests beautifulsoup4 lxml
"""

import sys
import os
import re
import time
import argparse
import tempfile
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import pdfplumber                     # pip install pdfplumber
from bs4 import BeautifulSoup

from app.db.session import SessionLocal
from app.db.models import Report
from data_pipeline.strict_filter import score_relevance

# ── HTTP ───────────────────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; AcademicResearchBot/1.0; "
        "+https://github.com/youruniversity/safetravel-lk)"
    ),
    "Accept": "application/pdf, text/html, */*",
}
DOWNLOAD_TIMEOUT = 60   # PDFs can be large

# ── Sri Lanka geo lookup (same as news scraper) ────────────────────────────────
SL_GEO = {
    "colombo":        (6.9271,  79.8612),
    "kandy":          (7.2906,  80.6337),
    "galle":          (6.0535,  80.2210),
    "ella":           (6.8728,  81.0464),
    "sigiriya":       (7.9573,  80.7600),
    "negombo":        (7.2083,  79.8358),
    "mirissa":        (5.9483,  80.4716),
    "arugam bay":     (6.8399,  81.8325),
    "nuwara eliya":   (6.9497,  80.7891),
    "trincomalee":    (8.5874,  81.2152),
    "hikkaduwa":      (6.1395,  80.1061),
    "unawatuna":      (5.9997,  80.2489),
    "bentota":        (6.4221,  80.0009),
    "matara":         (5.9549,  80.5550),
    "jaffna":         (9.6615,  80.0255),
    "dambulla":       (7.8675,  80.6517),
    "anuradhapura":   (8.3114,  80.4037),
    "polonnaruwa":    (7.9403,  81.0188),
    "badulla":        (6.9934,  81.0550),
    "tangalle":       (6.0233,  80.7992),
    "weligama":       (5.9751,  80.4295),
    "yala":           (6.3744,  81.5219),
    "pinnawala":      (7.2994,  80.3478),
    "haputale":       (6.7699,  80.9606),
    "mount lavinia":  (6.8389,  79.8670),
    "batticaloa":     (7.7167,  81.7000),
    "ampara":         (7.2975,  81.6724),
    "hambantota":     (6.1241,  81.1185),
    "ratnapura":      (6.7056,  80.3847),
    "kurunegala":     (7.4863,  80.3647),
    "monaragala":     (6.8728,  81.3507),
    "kalutara":       (6.5854,  79.9607),
    "gampaha":        (7.0917,  80.0000),
    "kegalle":        (7.2513,  80.3464),
    "sri lanka":      (7.8731,  80.7718),   # fallback centre
}


def extract_geo(text: str) -> tuple:
    t = text.lower()
    for loc, (lat, lon) in SL_GEO.items():
        if loc in t:
            return loc.title(), lat, lon
    return "Sri Lanka", 7.8731, 80.7718


def clean_text(text: str) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


# ══════════════════════════════════════════════════════════════════════════════
#  KNOWN SLTDA / TOURIST POLICE PDF SOURCES
# ══════════════════════════════════════════════════════════════════════════════

KNOWN_PDF_SOURCES = [
    {
        "slug":   "sltda_official",
        "label":  "SLTDA Annual Statistical Report 2023",
        "weight": 0.97,
        "url":    "https://www.sltda.gov.lk/storage/common_media/AnnualStatisticalReport2023Final_1707817718.pdf",
    },
    {
        "slug":   "sltda_official",
        "label":  "SLTDA Annual Statistical Report 2022",
        "weight": 0.97,
        "url":    "https://www.sltda.gov.lk/storage/common_media/AnnualReport2022.pdf",
    },
    {
        "slug":   "sltda_official",
        "label":  "SLTDA Annual Statistical Report 2019",
        "weight": 0.97,
        "url":    "https://www.sltda.gov.lk/storage/common_media/Annual_Statistical_Report_2019.pdf",
    },
    {
        "slug":   "ministry_tourism_lk",
        "label":  "Ministry of Tourism Sri Lanka — Annual Report 2022",
        "weight": 0.92,
        "url":    "https://www.tourism.gov.lk/storage/annual_reports/annual_report_2022.pdf",
    },
    {
        "slug":   "fcdo_gov_uk",
        "label":  "UK FCDO Sri Lanka Travel Advice (PDF export)",
        "weight": 1.00,
        "url":    "https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/sri-lanka-travel-advice.pdf",
        "manual_note": (
            "This URL may be stale. To get the current PDF: visit "
            "https://www.gov.uk/foreign-travel-advice/sri-lanka, "
            "then use browser Print → Save as PDF."
        ),
    },
]

SAFETY_PARAGRAPH_KEYWORDS = [
    "complaint", "incident", "report", "case", "offence", "offense",
    "arrested", "prosecuted", "penalised", "violation",
    "scam", "fraud", "overcharge", "overcharged", "cheat", "cheated",
    "rip off", "touts", "touting", "unlicensed guide", "unauthorised",
    "harassment", "assault", "theft", "robbery", "pickpocket",
    "gem", "jewellery", "jewelry",
    "safety", "security", "warning", "caution", "risk", "danger",
    "avoid", "beware", "advisory", "alert",
    "tourist", "tourists", "visitor", "visitors", "traveller", "traveler",
    "foreign national", "foreigner",
    "sltda", "tourist police", "tourist board", "tourism authority",
    "licensed", "unlicensed", "registered",
]

MIN_PARAGRAPH_WORDS = 20
CONTEXT_WINDOW = 2


def extract_text_from_pdf(pdf_path: str, debug: bool = False) -> str:
    all_text = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            print(f"    PDF has {len(pdf.pages)} pages")
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text:
                    all_text.append(text)
                    if debug:
                        print(f"\n--- Page {i+1} ---\n{text[:500]}")
    except Exception as e:
        print(f"    ❌ pdfplumber failed: {e}")
        return ""

    return "\n\n".join(all_text)


def extract_tables_from_pdf(pdf_path: str) -> list:
    records = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                tables = page.extract_tables()
                for table in tables:
                    if not table or len(table) < 2:
                        continue

                    header_text = " ".join(
                        str(cell or "").lower() for cell in (table[0] or [])
                    )
                    if not any(k in header_text for k in [
                        "complaint", "incident", "offence", "crime", "scam",
                        "type", "category", "tourist", "violation"
                    ]):
                        continue

                    headers = [str(h or "").strip() for h in table[0]]

                    for row in table[1:]:
                        if not row or not any(cell for cell in row):
                            continue

                        cells = [str(c or "").strip() for c in row]
                        row_dict = dict(zip(headers, cells))

                        if not cells[0] or cells[0].isdigit():
                            continue

                        desc_parts = []
                        for col, val in row_dict.items():
                            if col and val and val not in ("", "-", "N/A"):
                                desc_parts.append(f"{col}: {val}")

                        if desc_parts:
                            text = f"SLTDA Statistical Record — {' | '.join(desc_parts)}"
                            records.append({
                                "title": f"SLTDA Complaint/Incident Record (Page {page_num + 1})",
                                "content": text,
                                "url": None,
                                "summary": text,
                            })
    except Exception as e:
        print(f"    ⚠ Table extraction failed: {e}")

    return records


def split_into_paragraphs(text: str) -> list:
    paras = re.split(r"\n{2,}", text)
    result = []
    for para in paras:
        para = clean_text(para)
        if len(para.split()) > 200:
            sentences = re.split(r"(?<=[.!?])\s+", para)
            chunk = []
            for sent in sentences:
                chunk.append(sent)
                if len(" ".join(chunk).split()) >= 60:
                    result.append(" ".join(chunk))
                    chunk = []
            if chunk:
                result.append(" ".join(chunk))
        else:
            result.append(para)
    return [p for p in result if p]


def extract_safety_paragraphs(full_text: str, debug: bool = False) -> list:
    paragraphs = split_into_paragraphs(full_text)
    records = []
    seen_paras = set()

    for i, para in enumerate(paragraphs):
        if len(para.split()) < MIN_PARAGRAPH_WORDS:
            continue

        para_lower = para.lower()
        if not any(kw in para_lower for kw in SAFETY_PARAGRAPH_KEYWORDS):
            continue

        start = max(0, i - CONTEXT_WINDOW)
        end   = min(len(paragraphs), i + CONTEXT_WINDOW + 1)
        context_text = " ".join(paragraphs[start:end])
        context_text = clean_text(context_text)

        key = context_text[:100]
        if key in seen_paras:
            continue
        seen_paras.add(key)

        if debug:
            print(f"\n[PARA MATCH] {para[:120]}...")

        first_sent = re.split(r"(?<=[.!?])\s+", para)[0][:120]
        title = f"SLTDA/Official Report — {first_sent}"

        records.append({
            "title": title,
            "content": context_text[:3000],
            "url": None,
            "summary": para[:300],
        })

    return records


def download_pdf(url: str, dest_path: str) -> bool:
    print(f"    Downloading: {url}")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=DOWNLOAD_TIMEOUT, stream=True)
        if resp.status_code != 200:
            print(f"    ⚠ HTTP {resp.status_code} — cannot download")
            return False

        content_type = resp.headers.get("Content-Type", "")
        if "pdf" not in content_type and not url.lower().endswith(".pdf"):
            print(f"    ⚠ Response is not a PDF (Content-Type: {content_type})")
            return False

        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        size_kb = os.path.getsize(dest_path) / 1024
        print(f"    ✅ Downloaded ({size_kb:.0f} KB) → {dest_path}")
        return True

    except Exception as e:
        print(f"    ❌ Download failed: {e}")
        return False


def classify_scam_type(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ["gem scam", "gem shop", "jewellery", "jewelry"]):
        return "Gem / Jewellery Scam"
    if any(k in t for k in ["tuk tuk", "tuk-tuk", "three-wheeler", "trishaw"]):
        return "Tuk-Tuk / Transport Scam"
    if any(k in t for k in ["fake guide", "fake monk", "bogus guide", "unlicensed guide"]):
        return "Fake Guide / Impersonation"
    if any(k in t for k in ["taxi scam", "airport scam", "airport taxi"]):
        return "Transport Fraud"
    if any(k in t for k in ["overcharg", "ripped off", "overpriced", "inflated price", "tout"]):
        return "Overcharging"
    if any(k in t for k in ["pickpocket", "bag snatch", "stolen", "mugged", "robbed", "theft"]):
        return "Theft / Robbery"
    if any(k in t for k in ["harass", "assault", "attack", "groped", "followed"]):
        return "Harassment / Assault"
    if any(k in t for k in ["food poison", "drugged", "spiked"]):
        return "Food / Drink Spiking"
    if any(k in t for k in ["accommodation scam", "guesthouse scam", "hotel scam"]):
        return "Accommodation Scam"
    if any(k in t for k in ["complaint", "violation", "offence", "statistical"]):
        return "Safety Advisory (Non-Incident)"
    return "General Safety Incident"


def ingest_records_to_db(
    records:      list,
    source_slug:  str,
    source_weight: float,
    db,
    dry_run:      bool = False,
) -> tuple:
    inserted = rejected = duped = 0

    for rec in records:
        title   = (rec.get("title")   or "").strip()
        content = (rec.get("content") or "").strip()
        url     = (rec.get("url")     or "")

        if len(content) < 30:
            content = f"{title}. {rec.get('summary', '')}".strip()
        if len(content) < 20:
            rejected += 1
            continue

        scoring = score_relevance(title, content)
        if source_weight >= 0.90:
            passes = scoring["geo_match"] and scoring["negative_score"] > 0
            if not passes and not scoring["geo_match"]:
                rejected += 1
                continue
            passes = scoring["geo_match"]
        else:
            passes = scoring["passes"]

        if not passes:
            rejected += 1
            continue

        if url and db.query(Report).filter(Report.url == url).first():
            duped += 1
            continue

        if title and db.query(Report).filter(Report.title.ilike(f"%{title[:60]}%")).first():
            duped += 1
            continue

        loc_name, lat, lon = extract_geo(f"{title} {content}")
        scam_type  = classify_scam_type(f"{title} {content}")
        body_lower = content.lower()
        risk_level = (
            3 if any(k in body_lower for k in ["kill", "murder", "stabbed", "serious injury"])
            else 2 if any(k in body_lower for k in ["assault", "robbed", "harass", "attack"])
            else 1
        )

        if dry_run:
            print(f"\n  [DRY RUN] Would insert:")
            print(f"    Title  : {title[:80]}")
            print(f"    Type   : {scam_type}")
            print(f"    Loc    : {loc_name} ({lat:.4f}, {lon:.4f})")
            print(f"    Weight : {source_weight}")
            print(f"    Content: {content[:200]}...")
            inserted += 1
            continue

        report = Report(
            source=source_slug,
            url=url or None,
            title=title or "SLTDA Official Record",
            content=content[:3000],
            latitude=lat,
            longitude=lon,
            is_scam=True,
            scam_type=scam_type,
            risk_level=risk_level,
            sentiment_score=-0.55,
            location_name=loc_name,
            source_weight=source_weight,
            demographic_target="Tourists",
        )
        db.add(report)
        inserted += 1
        if inserted % 5 == 0:
            db.commit()

    if not dry_run:
        db.commit()

    return inserted, rejected, duped


def process_pdf(
    pdf_path:     str,
    source_slug:  str,
    source_weight: float,
    label:        str,
    db,
    dry_run:      bool = False,
    debug:        bool = False,
) -> tuple:
    print(f"\n  Processing: {label}")
    print(f"  Path : {pdf_path}")
    print(f"  Slug : {source_slug} (weight={source_weight})")

    full_text = extract_text_from_pdf(pdf_path, debug=debug)
    if not full_text:
        print("  ⚠ No text extracted — PDF may be scanned/image-based.")
        return 0, 0, 0

    print(f"  Extracted {len(full_text.split()):,} words from PDF text")

    table_records = extract_tables_from_pdf(pdf_path)
    print(f"  Found {len(table_records)} safety-relevant table rows")

    para_records = extract_safety_paragraphs(full_text, debug=debug)
    print(f"  Found {len(para_records)} safety-relevant paragraphs")

    all_records = table_records + para_records
    print(f"  Total candidates: {len(all_records)}")

    if not all_records:
        print("  ⚠ No safety-relevant content found. Try --debug to inspect raw text.")
        return 0, 0, 0

    ins, rej, dup = ingest_records_to_db(
        records=all_records,
        source_slug=source_slug,
        source_weight=source_weight,
        db=db,
        dry_run=dry_run,
    )

    status = "✅" if ins > 0 else "⚪"
    mode   = "[DRY RUN] " if dry_run else ""
    print(f"  {status} {mode}{label}: +{ins} saved | {rej} filtered | {dup} duplicates")
    return ins, rej, dup


def main():
    parser = argparse.ArgumentParser(
        description="SLTDA / Tourist Police PDF Ingester — SafeTravel LK"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--auto",
        action="store_true",
        help="Auto-download and process all known SLTDA/Tourist Police PDFs",
    )
    mode.add_argument(
        "--pdf",
        metavar="PATH",
        help="Path to a local PDF file to ingest",
    )
    mode.add_argument(
        "--url",
        metavar="URL",
        help="URL of a PDF to download and ingest",
    )
    parser.add_argument(
        "--slug",
        default="sltda_official",
        help="Source slug for manual --pdf/--url mode (default: sltda_official)",
    )
    parser.add_argument(
        "--weight",
        type=float,
        default=0.97,
        help="Source credibility weight for manual mode (default: 0.97)",
    )
    parser.add_argument(
        "--label",
        default="Manual PDF Import",
        help="Human-readable label for this PDF source",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be inserted without writing to DB",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print raw extracted text and paragraph matches",
    )

    args = parser.parse_args()
    db   = SessionLocal()

    print("=" * 68)
    print("  SafeTravel LK — SLTDA / Tourist Police PDF Ingester")
    mode_str = "AUTO" if args.auto else ("URL" if args.url else "LOCAL PDF")
    print(f"  Mode: {mode_str} | Dry run: {args.dry_run}")
    print("=" * 68)

    total_ins = total_rej = total_dup = 0

    try:
        if args.auto:
            print(f"\n  Processing {len(KNOWN_PDF_SOURCES)} known PDF sources...")
            for source in KNOWN_PDF_SOURCES:
                if "manual_note" in source:
                    print(f"\n  ⚠ [{source['label']}] Manual download required:")
                    print(f"     {source['manual_note']}")
                    print(f"     Once downloaded, run: python -m data_pipeline.ingest_sltda_pdf "
                          f"--pdf <path> --slug {source['slug']} --weight {source['weight']}")
                    continue

                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp_path = tmp.name

                try:
                    ok = download_pdf(source["url"], tmp_path)
                    if not ok:
                        continue

                    ins, rej, dup = process_pdf(
                        pdf_path=tmp_path,
                        source_slug=source["slug"],
                        source_weight=source["weight"],
                        label=source["label"],
                        db=db,
                        dry_run=args.dry_run,
                        debug=args.debug,
                    )
                    total_ins += ins
                    total_rej += rej
                    total_dup += dup

                    time.sleep(2.0)

                finally:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)

        elif args.url:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp_path = tmp.name

            try:
                ok = download_pdf(args.url, tmp_path)
                if ok:
                    ins, rej, dup = process_pdf(
                        pdf_path=tmp_path,
                        source_slug=args.slug,
                        source_weight=args.weight,
                        label=args.label or args.url,
                        db=db,
                        dry_run=args.dry_run,
                        debug=args.debug,
                    )
                    total_ins += ins
                    total_rej += rej
                    total_dup += dup
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        else:
            if not os.path.isfile(args.pdf):
                print(f"❌ File not found: {args.pdf}")
                sys.exit(1)

            ins, rej, dup = process_pdf(
                pdf_path=args.pdf,
                source_slug=args.slug,
                source_weight=args.weight,
                label=args.label,
                db=db,
                dry_run=args.dry_run,
                debug=args.debug,
            )
            total_ins += ins
            total_rej += rej
            total_dup += dup

    finally:
        db.close()

    print("\n" + "=" * 68)
    dry_str = " [DRY RUN — nothing written]" if args.dry_run else ""
    print(f"  PDF INGEST COMPLETE{dry_str}")
    print(f"  Total saved   : {total_ins}")
    print(f"  Total filtered: {total_rej}")
    print(f"  Total duped   : {total_dup}")
    if total_ins > 0:
        print(f"\n  ✅ These are Tier-0/Tier-1 records with weight 0.92–1.00.")
        print(f"     They will significantly improve your credibility tier distribution.")
    print("=" * 68)


if __name__ == "__main__":
    main()
