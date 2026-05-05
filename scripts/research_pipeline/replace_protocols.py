#!/usr/bin/env python3
"""Replace stub protocol data in municipal_positions.html with rich data from protocol_findings.js."""

import re
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FINDINGS_PATH = ROOT / 'protocol_findings.js'
HTML_PATH = ROOT / 'municipal_positions.html'

# Step 1: Parse protocol_findings.js using regex to extract field values directly
with open(FINDINGS_PATH, 'r', encoding='utf-8') as f:
    js_content = f.read()

# Extract just the findings array text
findings_match = re.search(r'findings:\s*\[(.*?)\]\s*,\s*proposers:', js_content, re.DOTALL)
if not findings_match:
    raise ValueError("Could not find findings array in protocol_findings.js")

findings_text = findings_match.group(1)

# Remove JS comments (but not // inside strings like URLs)
# Walk character by character, tracking whether we're inside a string
cleaned = []
i = 0
in_string = False
escape_next = False
while i < len(findings_text):
    ch = findings_text[i]
    if escape_next:
        cleaned.append(ch)
        escape_next = False
        i += 1
        continue
    if ch == '\\' and in_string:
        cleaned.append(ch)
        escape_next = True
        i += 1
        continue
    if ch == '"':
        in_string = not in_string
        cleaned.append(ch)
        i += 1
        continue
    if not in_string and ch == '/' and i + 1 < len(findings_text) and findings_text[i+1] == '/':
        # Skip to end of line
        while i < len(findings_text) and findings_text[i] != '\n':
            i += 1
        continue
    cleaned.append(ch)
    i += 1
findings_text = ''.join(cleaned)

# Split into individual object blocks by tracking braces
finding_blocks = []
brace_depth = 0
current_start = None
for i, ch in enumerate(findings_text):
    if ch == '{':
        if brace_depth == 0:
            current_start = i
        brace_depth += 1
    elif ch == '}':
        brace_depth -= 1
        if brace_depth == 0 and current_start is not None:
            finding_blocks.append(findings_text[current_start:i+1])
            current_start = None

def extract_field(block, field_name):
    """Extract a field value from a JS object block.
    Handles: string values (with escaped quotes), null, numbers."""
    # Try quoted string value first
    # The key is unquoted in JS: field_name: "value"
    # Value may contain escaped quotes \"
    pattern = rf'\b{re.escape(field_name)}\s*:\s*"((?:[^"\\]|\\.)*)"'
    m = re.search(pattern, block, re.DOTALL)
    if m:
        val = m.group(1)
        # Clean up: replace literal newlines with spaces
        val = val.replace('\n', ' ').replace('\r', ' ')
        return val

    # Try null
    pattern = rf'\b{re.escape(field_name)}\s*:\s*null'
    m = re.search(pattern, block)
    if m:
        return None

    # Try number
    pattern = rf'\b{re.escape(field_name)}\s*:\s*(\d+)'
    m = re.search(pattern, block)
    if m:
        return int(m.group(1))

    return None

findings = []
for block in finding_blocks:
    finding = {
        'city_he': extract_field(block, 'city_he'),
        'date': extract_field(block, 'date'),
        'summary_he': extract_field(block, 'summary_he'),
        'quote_he': extract_field(block, 'quote_he'),
        'outcome': extract_field(block, 'outcome'),
        'source_url': extract_field(block, 'source_url'),
        'category_he': extract_field(block, 'category_he'),
    }
    findings.append(finding)

print(f"Parsed {len(findings)} findings from protocol_findings.js")

# Step 2: Group findings by city_he
by_city = {}
for f in findings:
    city = f['city_he']
    if city not in by_city:
        by_city[city] = []
    by_city[city].append(f)

print(f"Cities with findings: {list(by_city.keys())}")
for city, items in by_city.items():
    print(f"  {city}: {len(items)} findings")

# Step 3: Build rich protocol entries per city
def build_protocol_entry(finding):
    return {
        "summary": finding.get('summary_he') or '',
        "date": finding.get('date') or '',
        "vote": finding.get('outcome') or '',
        "quote": finding.get('quote_he') or '',
        "url": finding.get('source_url') or '',
        "category": finding.get('category_he') or ''
    }

rich_protocols = {}
for city, items in by_city.items():
    rich_protocols[city] = [build_protocol_entry(f) for f in items]

# Step 4: Read the HTML and replace protocols
with open(HTML_PATH, 'r', encoding='utf-8') as f:
    html = f.read()

# Find the var cities = [...] block
cities_match = re.search(r'(var cities = \[)(.*?)(\];)', html, re.DOTALL)
if not cities_match:
    raise ValueError("Could not find var cities array in HTML")

cities_text = cities_match.group(2)

# For each city that has findings, replace its "protocols" array
replacements_made = 0
for city_name, protocols in rich_protocols.items():
    escaped_name = re.escape(city_name)

    # Find the city name in the text
    name_pattern = rf'"name":\s*"{escaped_name}"'
    name_match = re.search(name_pattern, cities_text)
    if not name_match:
        print(f"WARNING: Could not find city {city_name} in cities array")
        continue

    # Find "protocols": [ after this name
    proto_pattern = r'"protocols":\s*\['
    proto_match = re.search(proto_pattern, cities_text[name_match.start():])
    if not proto_match:
        print(f"WARNING: Could not find protocols for {city_name}")
        continue

    # Absolute position of the opening [
    bracket_start = name_match.start() + proto_match.end() - 1

    # Find matching ] by tracking bracket depth
    depth = 0
    bracket_end = None
    for i in range(bracket_start, len(cities_text)):
        if cities_text[i] == '[':
            depth += 1
        elif cities_text[i] == ']':
            depth -= 1
            if depth == 0:
                bracket_end = i
                break

    if bracket_end is None:
        print(f"WARNING: Could not find closing bracket for {city_name}")
        continue

    protocols_json = json.dumps(protocols, ensure_ascii=False)

    # Replace the [...] section
    cities_text = cities_text[:bracket_start] + protocols_json + cities_text[bracket_end+1:]
    replacements_made += 1
    print(f"Replaced protocols for {city_name} ({len(protocols)} findings)")

# Reconstruct the HTML
new_html = html[:cities_match.start(2)] + cities_text + html[cities_match.end(2):]

# Step 5: Write back
with open(HTML_PATH, 'w', encoding='utf-8') as f:
    f.write(new_html)

print(f"\nDone. Made {replacements_made} replacements.")
print(f"Output written to {HTML_PATH}")
