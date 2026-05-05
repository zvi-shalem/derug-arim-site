#!/usr/bin/env python3
"""
Clean municipal_positions.html: remove Gemini English metadata from position values,
cross-reference with research_unified.db for training tags, rebuild clean Hebrew strings.
"""

import re
import json
import sqlite3
import os

HTML_PATH = "/Users/zvishalem/derug-arim-site/municipal_positions.html"
DB_PATH = "/Users/zvishalem/derug-arim-site/research_unified.db"

# Training keywords to look for
TRAINING_KEYWORDS = {
    'מעוז': 'מעוז',
    'מנדל': 'מנדל',
    'Mandel': 'מנדל',
    'אבני ראשה': 'אבני ראשה',
    'וקסנר': 'וקסנר',
    'Wexner': 'וקסנר',
    'שוסטרמן': 'שוסטרמן',
    'Maoz': 'מעוז',
    'Avnei Rosha': 'אבני ראשה',
}


def extract_training_tags(text):
    """Extract training program tags from a string."""
    tags = set()
    for keyword, tag in TRAINING_KEYWORDS.items():
        if keyword in text:
            tags.add(tag)
    return tags


def clean_position_value(value):
    """
    Clean a single position value string.
    Returns (cleaned_hebrew, tags_from_string).
    """
    if not value or not value.strip():
        return "", set()

    # Extract training tags from the FULL string (including Gemini part) before removing
    tags = extract_training_tags(value)

    # Remove Gemini metadata: everything after "| Gemini:"
    # Pattern: " | Gemini: ..." at end of string or before next segment
    cleaned = re.sub(r'\s*\|\s*Gemini:.*$', '', value)

    # Also remove standalone English metadata patterns like "| Name, מ-YYYY, ..."
    # These are English-only entries without the "Gemini:" prefix
    # Pattern: " | EnglishName, מ-YYYY, English, English, English"
    cleaned = re.sub(r'\s*\|\s*[A-Za-z][A-Za-z\s\-\'\.]+,\s*מ-\d{4},.*$', '', cleaned)

    # Remove any remaining pure English segments at end (e.g., "| Michal Ohana, מ-2024, Education, Registrar, Professional")
    # But keep Hebrew content

    # Strip trailing whitespace
    cleaned = cleaned.strip()

    return cleaned, tags


def search_person_in_db(cursor, name_he):
    """
    Search for a person by Hebrew name in the DB.
    Returns (description, role, org_ids) or None.
    """
    if not name_he:
        return None

    # Clean the name for search - remove parenthetical notes, titles
    search_name = re.sub(r'\(.*?\)', '', name_he).strip()
    search_name = re.sub(r'^(ד"ר|דר|פרופ\'?|עו"ד|רו"ח)\s+', '', search_name).strip()
    # Remove role descriptions after dash
    search_name = re.sub(r'\s*—\s*.*$', '', search_name).strip()
    # Remove trailing comma and anything after
    search_name = re.sub(r',.*$', '', search_name).strip()
    # Handle slash-separated names (take first)
    if '/' in search_name and not search_name.startswith('/'):
        search_name = search_name.split('/')[0].strip()

    if not search_name or len(search_name) < 2:
        return None

    # Exact match first
    cursor.execute("SELECT description, role, org_ids FROM people WHERE name_he = ?", (search_name,))
    row = cursor.fetchone()
    if row:
        return row

    # Try LIKE match
    cursor.execute("SELECT description, role, org_ids FROM people WHERE name_he LIKE ?", (f"%{search_name}%",))
    row = cursor.fetchone()
    if row:
        return row

    return None


def extract_hebrew_name(cleaned_value):
    """Extract just the Hebrew name from a cleaned position value (for DB lookup)."""
    if not cleaned_value:
        return ""
    # Take everything before parentheses or dash
    name = re.split(r'\s*[\(—]', cleaned_value)[0].strip()
    # Handle "name / name" - take first
    if ' / ' in name:
        name = name.split(' / ')[0].strip()
    return name


def process_cities(cities, cursor):
    """Process all cities, cleaning position values and enriching with DB data."""
    changes = []

    for city in cities:
        city_name = city.get('name', '?')
        positions = city.get('positions', {})

        for pos_key, pos_value in positions.items():
            if not pos_value or not pos_value.strip():
                continue

            original = pos_value
            cleaned, string_tags = clean_position_value(pos_value)

            # Look up in DB
            hebrew_name = extract_hebrew_name(cleaned)
            db_tags = set()
            db_result = search_person_in_db(cursor, hebrew_name)
            if db_result:
                desc, role, org_ids = db_result
                if desc:
                    db_tags = extract_training_tags(desc)
                if role:
                    db_tags |= extract_training_tags(role)

            # Merge tags: from original string + from DB
            all_tags = string_tags | db_tags

            # Build final value
            final = cleaned

            # Add training tags if any found that aren't already mentioned in the cleaned text
            existing_tags_in_text = extract_training_tags(cleaned)
            new_tags = all_tags - existing_tags_in_text

            if new_tags:
                # Append tags section
                tag_str = ' / '.join(sorted(new_tags))
                # Check if text already has a tag section
                if '[תגיות:' in final:
                    # Append to existing
                    final = re.sub(r'\[תגיות:([^\]]*)\]',
                                   lambda m: f'[תגיות:{m.group(1).strip()}, {tag_str}]', final)
                else:
                    final = f"{final} [תגיות: {tag_str}]"

            if final != original:
                changes.append({
                    'city': city_name,
                    'position': pos_key,
                    'before': original,
                    'after': final
                })
                positions[pos_key] = final

    return changes


def main():
    # Read HTML
    with open(HTML_PATH, 'r', encoding='utf-8') as f:
        html = f.read()

    # Extract the cities array
    # Find "var cities = [" and the matching "];"
    match = re.search(r'(var cities = )(\[[\s\S]*?\}\]);', html)
    if not match:
        print("ERROR: Could not find cities array in HTML")
        return

    prefix = match.group(1)
    cities_json_str = match.group(2)
    start_pos = match.start()
    end_pos = match.end()

    # Parse JSON - need to handle JavaScript-style JSON
    # The array uses double quotes, should be valid JSON
    try:
        cities = json.loads(cities_json_str)
        print(f"Parsed {len(cities)} cities successfully")
    except json.JSONDecodeError as e:
        print(f"ERROR parsing cities JSON: {e}")
        # Try to find the issue
        print(f"Error at position {e.pos}: ...{cities_json_str[max(0,e.pos-50):e.pos+50]}...")
        return

    # Connect to DB
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Process
    changes = process_cities(cities, cursor)
    conn.close()

    print(f"\nTotal changes: {len(changes)}")
    for ch in changes:
        print(f"\n  [{ch['city']}] {ch['position']}:")
        print(f"    BEFORE: {ch['before'][:120]}...")
        print(f"    AFTER:  {ch['after'][:120]}...")

    if not changes:
        print("No changes needed.")
        return

    # Rebuild JSON
    new_json = json.dumps(cities, ensure_ascii=False, indent=0)

    # Format to match original style: compact but readable
    # The original uses newlines between fields, let's keep it similar
    # Actually, let's produce a format close to the original
    new_cities_block = format_cities_js(cities)

    # Verify the new JSON parses
    try:
        # Extract just the array part for verification
        verify_json = new_cities_block
        parsed = json.loads(verify_json)
        print(f"\nVerification: parsed {len(parsed)} cities from output - OK")
    except json.JSONDecodeError as e:
        print(f"\nERROR: Output JSON failed to parse: {e}")
        return

    # Replace in HTML
    new_html = html[:start_pos] + prefix + new_cities_block + ";" + html[end_pos:]

    # Backup original
    backup_path = HTML_PATH + '.bak'
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Backup saved to {backup_path}")

    # Write new HTML
    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(new_html)
    print(f"Updated {HTML_PATH}")


def format_cities_js(cities):
    """Format cities array in a JS-friendly way matching original style."""
    parts = []
    for city in cities:
        lines = []
        lines.append('{')
        lines.append(f'"name": {json.dumps(city["name"], ensure_ascii=False)},')
        lines.append('"positions": {')

        pos_lines = []
        for key, val in city['positions'].items():
            pos_lines.append(f'"{key}": {json.dumps(val, ensure_ascii=False)}')
        lines.append(',\n'.join(pos_lines))
        lines.append('},')

        # Protocols
        if city.get('protocols'):
            lines.append(f'"protocols": {json.dumps(city["protocols"], ensure_ascii=False)},')
        else:
            lines.append('"protocols": [],')

        # Source URLs
        if city.get('source_urls'):
            lines.append(f'"source_urls": {json.dumps(city["source_urls"], ensure_ascii=False)}')
        else:
            lines.append('"source_urls": {}')

        lines.append('\n}')
        parts.append('\n'.join(lines))

    return '[' + ',\n'.join(parts) + ']'


if __name__ == '__main__':
    main()
