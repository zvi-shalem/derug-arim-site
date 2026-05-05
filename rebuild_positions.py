#!/usr/bin/env python3
"""
Rebuild municipal_positions.html with source annotations from city_grid.source_urls.
Reads existing HTML, injects source_urls into city data, adds source link rendering.
"""
import sqlite3
import json
import time
import re

DB_PATH = "/Users/zvishalem/derug-arim-site/research_unified.db"
HTML_PATH = "/Users/zvishalem/derug-arim-site/municipal_positions.html"

def get_sources():
    """Get source_urls from DB for all cities."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT city, source_urls FROM city_grid ORDER BY city")
    sources = {}
    for row in cur.fetchall():
        if row[1]:
            sources[row[0]] = json.loads(row[1])
        else:
            sources[row[0]] = {}
    conn.close()
    return sources

def rebuild():
    sources = get_sources()

    with open(HTML_PATH, 'r', encoding='utf-8') as f:
        html = f.read()

    version = int(time.time() * 1000)

    # Update version
    html = re.sub(r'content="(\d+)"', f'content="{version}"', html, count=1)
    html = re.sub(r'const FILE_VERSION=\d+', f'const FILE_VERSION={version}', html)

    # Inject source_urls into each city object in the cities array
    # Find the cities array and parse it
    cities_match = re.search(r'var cities = \[(.*?)\];', html, re.DOTALL)
    if not cities_match:
        print("ERROR: Could not find cities array")
        return

    cities_str = cities_match.group(1)

    # Parse each city block and inject source_urls
    # Strategy: find each city object and add source_urls field
    city_blocks = []
    depth = 0
    current = ""
    for char in cities_str:
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
        current += char
        if depth == 0 and current.strip():
            if current.strip().startswith('{'):
                city_blocks.append(current.strip().rstrip(','))
            current = ""

    new_blocks = []
    for block in city_blocks:
        # Extract city name
        name_match = re.search(r'"name":\s*"([^"]+)"', block)
        if not name_match:
            new_blocks.append(block)
            continue

        city_name = name_match.group(1)
        city_sources = sources.get(city_name, {})

        # Add source_urls field before the closing of the top-level object
        source_json = json.dumps(city_sources, ensure_ascii=False)

        # Insert source_urls after "protocols": [...]
        # Find the last ] before the final }
        last_bracket = block.rfind(']')
        if last_bracket != -1:
            new_block = block[:last_bracket+1] + ',\n"source_urls": ' + source_json + '\n' + block[last_bracket+1:]
        else:
            new_block = block

        new_blocks.append(new_block)

    new_cities_str = ',\n'.join(new_blocks)
    html = html[:cities_match.start(1)] + new_cities_str + html[cities_match.end(1):]

    # Add new stat for sources
    stats_addition = '''    <div class="stat-item"><div class="stat-number source" id="stat-sources">0</div><div class="stat-label">מקורות מאומתים</div></div>
'''
    html = html.replace('</div>\n<div class="filters">', stats_addition + '</div>\n<div class="filters">')

    # Add source filter button
    source_filter = '    <button class="filter-btn source" data-filter="sourced">עם מקורות</button>\n'
    html = html.replace('    <button class="filter-btn protocol"', source_filter + '    <button class="filter-btn protocol"')

    # Add CSS for source styling
    source_css = '''
        .stat-number.source { color: #27ae60; }
        .filter-btn.source { border-color: #27ae60; color: #27ae60; }
        .filter-btn.source:hover, .filter-btn.source.active { background: #27ae60; color: white; }
        .source-link { display: inline-block; margin-right: 6px; font-size: 0.8em; vertical-align: middle; }
        .source-link a { color: #27ae60; text-decoration: none; font-weight: 600; }
        .source-link a:hover { text-decoration: underline; }
        .source-missing { display: inline-block; margin-right: 6px; font-size: 0.75em; color: #bbb; font-style: italic; }
'''
    html = html.replace('@media (max-width: 768px)', source_css + '        @media (max-width: 768px)')

    # Modify hasMaoz section to add hasSources function
    html = html.replace(
        'function hasProtocol(c) { return c.protocols.length > 0; }',
        'function hasProtocol(c) { return c.protocols.length > 0; }\nfunction hasSource(c) { return c.source_urls && Object.keys(c.source_urls).length > 0; }'
    )

    # Modify renderCity to add source annotations to position items
    # Replace the position rendering loop
    old_render = '''var v = c.positions[k], empty = !v || v.trim() === "";
        ph += '<div class="position-item' + (empty ? " empty" : "") + '"><div class="position-title">' + positionNames[k] + '</div><div class="position-value">' + (empty ? "לא ידוע" : hl(v)) + '</div></div>';'''

    new_render = '''var v = c.positions[k], empty = !v || v.trim() === "";
        var srcUrl = c.source_urls && c.source_urls[k];
        var srcHtml = "";
        if (!empty) {
            if (srcUrl) {
                srcHtml = '<span class="source-link"><a href="' + srcUrl + '" target="_blank" title="מקור מאומת">&#128279; מקור</a></span>';
            } else {
                srcHtml = '<span class="source-missing">מקור חסר</span>';
            }
        }
        ph += '<div class="position-item' + (empty ? " empty" : "") + '"><div class="position-title">' + positionNames[k] + ' ' + srcHtml + '</div><div class="position-value">' + (empty ? "לא ידוע" : hl(v)) + '</div></div>';'''

    html = html.replace(old_render, new_render)

    # Add source_urls to dataset for filtering
    html = html.replace(
        'card.dataset.protocol = hasProtocol(c) ? "1" : "0";',
        'card.dataset.protocol = hasProtocol(c) ? "1" : "0";\n    card.dataset.sourced = hasSource(c) ? "1" : "0";'
    )

    # Add source filter handling
    html = html.replace(
        'else if (activeFilter === "protocol") show = card.dataset.protocol === "1";',
        'else if (activeFilter === "protocol") show = card.dataset.protocol === "1";\n        else if (activeFilter === "sourced") show = card.dataset.sourced === "1";'
    )

    # Update computeStats to count sources
    old_stats = '''pr += c.protocols.length;
    });
    document.getElementById("stat-positions").textContent = pos;'''

    new_stats = '''pr += c.protocols.length;
        if (c.source_urls) { Object.keys(c.source_urls).forEach(function(k) { if (c.source_urls[k]) sr++; }); }
    });
    document.getElementById("stat-positions").textContent = pos;'''

    html = html.replace(old_stats, new_stats)

    html = html.replace(
        'var pos = 0, mz = 0, av = 0, pr = 0;',
        'var pos = 0, mz = 0, av = 0, pr = 0, sr = 0;'
    )

    html = html.replace(
        'document.getElementById("stat-protocols").textContent = pr;',
        'document.getElementById("stat-protocols").textContent = pr;\n    document.getElementById("stat-sources").textContent = sr;'
    )

    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(html)

    # Count stats
    total_sourced = sum(len(v) for v in sources.values())
    total_positions = 0
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for field in ["mayor", "edu_director", "edu_secondary", "gender_advisor", "ceo", "treasurer", "psych_services", "culture_director"]:
        cur.execute(f"SELECT COUNT(*) FROM city_grid WHERE {field} IS NOT NULL AND {field} != ''")
        total_positions += cur.fetchone()[0]
    conn.close()

    print(f"HTML rebuilt with version {version}")
    print(f"Sourced positions: {total_sourced}")
    print(f"Filled positions total: {total_positions}")
    print(f"Missing sources: {total_positions - total_sourced}")

if __name__ == "__main__":
    rebuild()
