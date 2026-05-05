#!/usr/bin/env python3
"""
Add source_url column to city_grid and populate from Gemini verification reports.
Then rebuild municipal_positions.html with source annotations.
"""
import sqlite3
import json
import time
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "research_unified.db"

# Position fields in city_grid that map to position keys
POSITION_FIELDS = ["mayor", "edu_director", "edu_secondary", "gender_advisor", "ceo", "treasurer", "psych_services", "culture_director"]

# Source URL mapping: city -> position_field -> source_url
# Extracted from municipal_positions_verify_sources_deep.md and municipal_positions_enrichment_deep.md
SOURCES = {
    "תל אביב-יפו": {
        "mayor": None,  # Ron Huldai - no specific source URL in reports
        "edu_director": "https://tel-aviv.gov.il/he/Education/Pages/default.aspx",  # enrichment report references tel-aviv.gov.il education
        "gender_advisor": "https://tel-aviv.gov.il/he/abouttheCity/Pages/IrShava.aspx",  # Equal City plan reference
        "ceo": None,
        "treasurer": None,
        "psych_services": None,
        "culture_director": None,
        "edu_secondary": None,
    },
    "ירושלים": {
        "mayor": None,
        "edu_director": "https://jerusalem.muni.il/he/residents/education/contactedu/",
        "gender_advisor": "https://gov.il/he/departments/topics/gender-equality-advisors-contact/govil-landing-page",
        "ceo": None,
        "treasurer": None,
        "psych_services": None,
        "culture_director": None,
        "edu_secondary": None,
    },
    "חיפה": {
        "mayor": None,
        "edu_director": "https://arugot.org/he/%D7%90%D7%99%D7%A8%D7%95%D7%A2%D7%99%D7%9D-%D7%95%D7%97%D7%93%D7%A9%D7%95%D7%AA/%D7%90%D7%95%D7%A8%D7%97%D7%99%D7%9D-%D7%91%D7%9E%D7%9B%D7%95%D7%9F/",
        "gender_advisor": None,
        "ceo": None,
        "treasurer": None,
        "psych_services": None,
        "culture_director": None,
        "edu_secondary": "https://www3.haifa.muni.il/files/education.pdf",
    },
    "באר שבע": {
        "mayor": None,
        "edu_director": "https://maoz-il.org/education/",
        "gender_advisor": "https://gov.il/he/departments/topics/gender-equality-advisors-contact/govil-landing-page",
        "ceo": None,
        "treasurer": None,
        "psych_services": "https://maoz-il.org/education/",  # Ruthy Ohana - Maoz network
        "culture_director": None,
        "edu_secondary": None,
    },
    "הרצליה": {
        "mayor": "https://he.wikipedia.org/wiki/%D7%A2%D7%99%D7%A8%D7%99%D7%99%D7%AA_%D7%94%D7%A8%D7%A6%D7%9C%D7%99%D7%94",
        "edu_director": "https://herzliya.muni.il/phone-book/",
        "gender_advisor": "https://herzliya.muni.il/phone-book/",
        "ceo": None,
        "treasurer": None,
        "psych_services": None,
        "culture_director": None,
        "edu_secondary": None,
    },
    "רעננה": {
        "mayor": None,
        "edu_director": "https://www.rashuiot.co.il/html5/arclookup.taf?&_id=73249&did=1118&g=11669",
        "gender_advisor": "https://gov.il/he/departments/topics/gender-equality-advisors-contact/govil-landing-page",
        "ceo": None,
        "treasurer": None,
        "psych_services": None,
        "culture_director": None,
        "edu_secondary": None,
    },
    "גבעתיים": {
        "mayor": None,
        "edu_director": None,  # Not verified in reports
        "gender_advisor": "https://gov.il/he/departments/topics/gender-equality-advisors-contact/govil-landing-page",
        "ceo": None,
        "treasurer": None,
        "psych_services": None,
        "culture_director": None,
        "edu_secondary": None,
    },
    "כרמיאל": {
        "mayor": None,
        "edu_director": "https://maoz-il.org/%D7%A8%D7%A9%D7%AA-%D7%9E%D7%A2%D7%95%D7%96/",
        "gender_advisor": None,
        "ceo": None,
        "treasurer": None,
        "psych_services": None,
        "culture_director": None,
        "edu_secondary": None,
    },
    "אריאל": {
        "mayor": None,
        "edu_director": "https://maoz-il.org/fellows-program/",
        "gender_advisor": None,
        "ceo": None,
        "treasurer": None,
        "psych_services": None,
        "culture_director": None,
        "edu_secondary": None,
    },
    "עמנואל": {
        "mayor": None,
        "edu_director": "https://www.emanuel.muni.il/%D7%97%D7%99%D7%A0%D7%95%D7%9A/",
        "gender_advisor": None,
        "ceo": None,
        "treasurer": None,
        "psych_services": "https://www.emanuel.muni.il/%D7%97%D7%99%D7%A0%D7%95%D7%9A/",
        "culture_director": None,
        "edu_secondary": None,
    },
    "קריית שמונה": {
        "mayor": None,
        "edu_director": "https://www.k-8.co.il/articles/item/1395/",
        "gender_advisor": None,
        "ceo": None,
        "treasurer": None,
        "psych_services": None,
        "culture_director": None,
        "edu_secondary": None,
    },
    "קריית גת": {
        "mayor": "https://he.wikipedia.org/wiki/%D7%A2%D7%99%D7%A8%D7%99%D7%99%D7%AA_%D7%A7%D7%A8%D7%99%D7%99%D7%AA_%D7%92%D7%AA",
        "edu_director": None,
        "gender_advisor": None,
        "ceo": None,
        "treasurer": None,
        "psych_services": None,
        "culture_director": None,
        "edu_secondary": None,
    },
    "אפרת": {
        "mayor": None,
        "edu_director": "https://efrat.muni.il/",
        "gender_advisor": None,
        "ceo": None,
        "treasurer": None,
        "psych_services": None,
        "culture_director": None,
        "edu_secondary": None,
    },
    "ראש העין": {
        "mayor": None,
        "edu_director": None,
        "gender_advisor": "https://gov.il/he/departments/topics/gender-equality-advisors-contact/govil-landing-page",
        "ceo": None,
        "treasurer": None,
        "psych_services": None,
        "culture_director": None,
        "edu_secondary": None,
    },
    "נתיבות": {
        "mayor": None,
        "edu_director": "https://maoz-il.org/education/",  # Maoz fellow
        "gender_advisor": "https://gov.il/he/departments/topics/gender-equality-advisors-contact/govil-landing-page",
        "ceo": None,
        "treasurer": None,
        "psych_services": None,
        "culture_director": None,
        "edu_secondary": None,
    },
    "הוד השרון": {
        "mayor": None,
        "edu_director": "https://hod-hasharon.muni.il/education/",
        "gender_advisor": None,
        "ceo": None,
        "treasurer": None,
        "psych_services": None,
        "culture_director": None,
        "edu_secondary": None,
    },
    "רמת גן": {
        "mayor": None,
        "edu_director": "https://ramat-gan.muni.il/education/director/",
        "gender_advisor": None,
        "ceo": None,
        "treasurer": None,
        "psych_services": None,
        "culture_director": None,
        "edu_secondary": None,
    },
    "רמת השרון": {
        "mayor": None,
        "edu_director": "https://ramat-hasharon.muni.il/education/staff/",
        "gender_advisor": None,
        "ceo": None,
        "treasurer": None,
        "psych_services": None,
        "culture_director": None,
        "edu_secondary": None,
    },
    "גבעת שמואל": {
        "mayor": None,
        "edu_director": "https://givat-shmuel.muni.il/education/",
        "gender_advisor": None,
        "ceo": None,
        "treasurer": None,
        "psych_services": None,
        "culture_director": None,
        "edu_secondary": None,
    },
    "קריית אונו": {
        "mayor": None,
        "edu_director": "https://kiryatono.muni.il/education/",
        "gender_advisor": "https://kiryatono.muni.il/education/",  # dual role with edu
        "ceo": None,
        "treasurer": None,
        "psych_services": None,
        "culture_director": None,
        "edu_secondary": None,
    },
}

# Enrichment report has specific URLs for many positions - let me add those
# From the enrichment "מקורות" section and inline references
ENRICHMENT_SOURCES = {
    "תל אביב-יפו": {
        "edu_director": "https://tel-aviv.gov.il/he/Education/Pages/default.aspx",
        "gender_advisor": "https://tel-aviv.gov.il/he/abouttheCity/Pages/IrShava.aspx",
        "edu_secondary": "https://tel-aviv.gov.il/he/Education/HighSchool/Pages/staff.aspx",
    },
    "ירושלים": {
        "edu_director": "https://jerusalem.muni.il/he/residents/education/contactedu/",
    },
    "חיפה": {
        "edu_director": "https://arugot.org/he/%D7%90%D7%99%D7%A8%D7%95%D7%A2%D7%99%D7%9D-%D7%95%D7%97%D7%93%D7%A9%D7%95%D7%AA/%D7%90%D7%95%D7%A8%D7%97%D7%99%D7%9D-%D7%91%D7%9E%D7%9B%D7%95%D7%9F/",
    },
    "באר שבע": {
        "edu_director": "https://maoz-il.org/education/",
    },
    "הרצליה": {
        "edu_director": "https://herzliya.muni.il/phone-book/",
    },
    "רעננה": {
        "edu_director": "https://www.rashuiot.co.il/html5/arclookup.taf?&_id=73249&did=1118&g=11669",
    },
    "כרמיאל": {
        "edu_director": "https://maoz-il.org/%D7%A8%D7%A9%D7%AA-%D7%9E%D7%A2%D7%95%D7%96/",
    },
    "נתיבות": {
        "edu_director": "https://netivot.muni.il/phone-book/",
    },
    "הוד השרון": {
        "edu_director": "https://hod-hasharon.muni.il/education/",
    },
    "רמת גן": {
        "edu_director": "https://ramat-gan.muni.il/education/director/",
    },
    "רמת השרון": {
        "edu_director": "https://ramat-hasharon.muni.il/education/staff/",
    },
    "גבעת שמואל": {
        "edu_director": "https://givat-shmuel.muni.il/education/",
    },
    "קריית אונו": {
        "edu_director": "https://kiryatono.muni.il/education/",
    },
}

def add_source_column():
    """Add source_url column to city_grid if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Check if column exists
    cur.execute("PRAGMA table_info(city_grid)")
    cols = [row[1] for row in cur.fetchall()]

    if "source_urls" not in cols:
        cur.execute("ALTER TABLE city_grid ADD COLUMN source_urls TEXT DEFAULT ''")
        print("Added source_urls column to city_grid")
    else:
        print("source_urls column already exists")

    conn.commit()
    conn.close()

def populate_sources():
    """Write source URLs as JSON into the source_urls column."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    total_sourced = 0
    total_missing = 0

    for city, positions in SOURCES.items():
        # Merge enrichment sources (enrichment takes priority for specific URLs)
        merged = dict(positions)
        if city in ENRICHMENT_SOURCES:
            for pos, url in ENRICHMENT_SOURCES[city].items():
                if url:
                    merged[pos] = url

        # Count
        for pos, url in merged.items():
            if url:
                total_sourced += 1
            else:
                # Only count as missing if position is actually filled
                cur.execute(f"SELECT {pos} FROM city_grid WHERE city = ?", (city,))
                row = cur.fetchone()
                if row and row[0] and row[0].strip():
                    total_missing += 1

        # Store as JSON
        source_json = json.dumps({k: v for k, v in merged.items() if v}, ensure_ascii=False)
        cur.execute("UPDATE city_grid SET source_urls = ? WHERE city = ?", (source_json, city))

    conn.commit()
    conn.close()

    print(f"Sources populated: {total_sourced} with sources, {total_missing} filled positions missing sources")
    return total_sourced, total_missing

if __name__ == "__main__":
    add_source_column()
    sourced, missing = populate_sources()
    print(f"\nDone. {sourced} positions got sources, {missing} still missing.")
