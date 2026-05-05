#!/usr/bin/env python3
"""
Migrate existing research data into unified research_unified.db

Sources:
1. research.db (21MB — orgs, individuals, programs, evidence, connections, etc.)
2. reports_metadata.db (reports_metadata)
3. city_matrix.db (entities, entity_details, matrix_cells, city_entity_links)

Does NOT touch: programs_metadata MySQL on server

Usage:
    python scripts/research_pipeline/migrate_to_unified.py [--dry-run]
"""

import sqlite3
import json
import os
import sys
import shutil
from pathlib import Path

# Paths
ROOT = Path(__file__).resolve().parents[2]
UNIFIED_DB = ROOT / "research_unified.db"
SCHEMA_SQL = ROOT / "data/schemas/unified_schema.sql"

# Source databases — try multiple paths (21MB version FIRST)
RESEARCH_DB_PATHS = [
    Path.home() / "data/דירוג_ערים/research.db",
    ROOT / "research.db",
    Path.home() / "persistent-team/projects/city_ranking/research.db",
]

REPORTS_META_DB_PATHS = [
    ROOT / "research/reports_metadata.db",
]

CITY_MATRIX_DB_PATHS = [
    Path.home() / "persistent-team/projects/city_ranking/city_matrix.db",
    Path.home() / "persistent-team/projects/דירוג_ערים/city_matrix.db",
    Path.home() / "data/city_matrix.db",
]


def find_db(paths, name):
    """Find first existing DB from list of candidate paths."""
    for p in paths:
        if p.exists() and p.stat().st_size > 0:
            print(f"  Found {name}: {p} ({p.stat().st_size:,} bytes)")
            return p
    print(f"  WARNING: {name} not found at any of: {[str(p) for p in paths]}")
    return None


def migrate_reports_metadata(unified, reports_meta_path):
    """Migrate reports_metadata → organizations + reports tables."""
    if not reports_meta_path:
        return 0, 0

    src = sqlite3.connect(reports_meta_path)
    src.row_factory = sqlite3.Row
    rows = src.execute("SELECT * FROM reports_metadata").fetchall()

    org_count = 0
    report_count = 0

    for row in rows:
        # Insert into organizations
        unified.execute("""
            INSERT OR IGNORE INTO organizations
            (name_he, name_en, org_type, year_founded, budget_ils, funding_sources,
             risk_level, summary_he, source_urls, report_filename)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row['name_he'],
            row['name_en'],
            row['org_type'],
            row['year_founded'],
            row['budget_ils'],
            row['funding_sources'],
            row['risk_level'],
            row['summary_he'],
            row['source_urls'] if 'source_urls' in row.keys() else None,
            row['filename'],
        ))
        org_id = unified.execute(
            "SELECT id FROM organizations WHERE report_filename=?", (row['filename'],)
        ).fetchone()[0]
        org_count += 1

        # Insert into reports
        unified.execute("""
            INSERT OR IGNORE INTO reports (filename, name_he, name_en, org_id, translated)
            VALUES (?, ?, ?, ?, ?)
        """, (
            row['filename'],
            row['name_he'],
            row['name_en'],
            org_id,
            row['translated'],
        ))
        report_count += 1

        # Parse connected_orgs and create connections
        if row['connected_orgs']:
            try:
                connected = json.loads(row['connected_orgs'])
                for org_name in connected:
                    unified.execute("""
                        INSERT OR IGNORE INTO organizations (name_he) VALUES (?)
                    """, (org_name,))
                    target = unified.execute(
                        "SELECT id FROM organizations WHERE name_he=?", (org_name,)
                    ).fetchone()
                    if target:
                        unified.execute("""
                            INSERT OR IGNORE INTO connections
                            (source_type, source_id, target_type, target_id, relation)
                            VALUES ('org', ?, 'org', ?, 'connected')
                        """, (org_id, target[0]))
            except json.JSONDecodeError:
                pass

        # Parse key_people and create people entries
        if row['key_people']:
            try:
                people = json.loads(row['key_people'])
                for person_name in people:
                    unified.execute("""
                        INSERT OR IGNORE INTO people (name_he, org_ids)
                        VALUES (?, ?)
                    """, (person_name, json.dumps([org_id])))
            except json.JSONDecodeError:
                pass

        # Parse domains and store in concepts
        if row['domains']:
            try:
                domains = json.loads(row['domains'])
                for domain in domains:
                    unified.execute("""
                        INSERT OR IGNORE INTO concepts
                        (name_he, concept_type, related_org_ids)
                        VALUES (?, 'domain', ?)
                    """, (domain, json.dumps([org_id])))
            except json.JSONDecodeError:
                pass

    src.close()
    return org_count, report_count


def migrate_city_matrix_entities(unified, city_matrix_path):
    """Migrate entity_details from city_matrix.db → organizations + people."""
    if not city_matrix_path:
        return 0

    src = sqlite3.connect(city_matrix_path)
    src.row_factory = sqlite3.Row

    count = 0

    # Migrate entities and entity_details
    entities = src.execute("""
        SELECT e.*, ed.summary, ed.entity_type as detail_type,
               ed.facts, ed.key_people, ed.connections as ed_connections,
               ed.budget, ed.programs as ed_programs, ed.sources as ed_sources
        FROM entities e
        LEFT JOIN entity_details ed ON ed.entity_id = e.id
    """).fetchall()

    for ent in entities:
        ent_type = ent['detail_type'] or ent['entity_type'] or 'org'

        if ent_type in ('org', 'program', 'term', 'forum', 'movement'):
            existing = unified.execute(
                "SELECT id FROM organizations WHERE name_he=?", (ent['name'],)
            ).fetchone()

            if existing:
                if ent['summary']:
                    unified.execute("""
                        UPDATE organizations SET summary_he = COALESCE(summary_he, ?)
                        WHERE id = ? AND (summary_he IS NULL OR summary_he = '')
                    """, (ent['summary'], existing[0]))
            else:
                unified.execute("""
                    INSERT OR IGNORE INTO organizations
                    (name_he, org_type, summary_he, budget_ils, source_urls)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    ent['name'],
                    ent_type,
                    ent['summary'],
                    ent['budget'],
                    ent['ed_sources'],
                ))
            count += 1

        elif ent_type == 'person':
            unified.execute("""
                INSERT OR IGNORE INTO people (name_he, description, source_urls)
                VALUES (?, ?, ?)
            """, (
                ent['name'],
                ent['summary'],
                ent['ed_sources'],
            ))
            count += 1

    # Migrate city_entity_links as connections
    links = src.execute("SELECT * FROM city_entity_links").fetchall()
    for link in links:
        unified.execute("""
            INSERT OR IGNORE INTO connections
            (source_type, source_id, target_type, target_id, relation, evidence)
            VALUES ('org', ?, 'org', 0, 'city_link', ?)
        """, (
            link['org_id'],
            json.dumps({
                'city': link['city'],
                'domain': link['cell_domain'],
                'dimension': link['cell_dimension'],
                'context': link['context_text'],
            }),
        ))

    src.close()
    return count


def migrate_research_files(unified, research_db_path):
    """Migrate research_files + city_markers from research.db → sources table."""
    if not research_db_path:
        return 0

    src = sqlite3.connect(research_db_path)
    src.row_factory = sqlite3.Row

    count = 0

    # research_files → sources
    files = src.execute("SELECT * FROM research_files").fetchall()
    for f in files:
        unified.execute("""
            INSERT OR IGNORE INTO sources
            (url, title, source_type, notes)
            VALUES (?, ?, ?, ?)
        """, (
            f['filename'],
            f['topic'],
            f['type'],
            json.dumps({
                'folder': f['folder'],
                'cities_mentioned': f['cities_mentioned'],
                'people_mentioned': f['people_mentioned'],
                'orgs_mentioned': f['orgs_mentioned'],
                'summary': f['summary'],
                'relevance_score': f['relevance_score'],
            }),
        ))
        count += 1

    # city_markers → sources
    markers = src.execute("SELECT * FROM city_markers").fetchall()
    for m in markers:
        unified.execute("""
            INSERT OR IGNORE INTO sources
            (url, title, source_type, entity_type, notes)
            VALUES (?, ?, 'marker', 'city', ?)
        """, (
            m['source'],
            f"{m['city']} - {m['marker_type']}",
            json.dumps({
                'city': m['city'],
                'marker_type': m['marker_type'],
                'status': m['status'],
                'year_adopted': m['year_adopted'],
                'decision_type': m['decision_type'],
                'details': m['details'],
            }),
        ))
        count += 1

    src.close()
    return count


def migrate_research_orgs(unified, research_db_path):
    """Migrate orgs from 21MB research.db → organizations table."""
    if not research_db_path:
        return 0

    src = sqlite3.connect(research_db_path)
    src.row_factory = sqlite3.Row

    count = 0
    updated = 0
    rows = src.execute("SELECT * FROM orgs").fetchall()

    # Also load assessments for risk/thesis data
    assessments = {}
    try:
        for a in src.execute("SELECT * FROM analysis_org_assessments").fetchall():
            assessments[a['org_id']] = a
    except Exception:
        pass

    for row in rows:
        # Check if already exists from reports_metadata
        existing = unified.execute(
            "SELECT id FROM organizations WHERE name_he=?", (row['name_he'],)
        ).fetchone()

        assessment = assessments.get(row['org_id'])
        risk_level = assessment['risk'] if assessment else None
        classification = None
        summary = assessment['thesis'] if assessment else None

        if existing:
            # Update fields that are empty
            unified.execute("""
                UPDATE organizations SET
                    name_en = COALESCE(name_en, ?),
                    org_type = COALESCE(org_type, ?),
                    year_founded = COALESCE(year_founded, ?),
                    budget_ils = COALESCE(budget_ils, ?),
                    funding_sources = COALESCE(funding_sources, ?),
                    risk_level = COALESCE(risk_level, ?),
                    classification = COALESCE(classification, ?),
                    website = COALESCE(website, ?),
                    source_urls = COALESCE(source_urls, ?)
                WHERE id = ? AND name_he = ?
            """, (
                row['name_en'],
                row['entity_type'],
                row['founded'],
                row['revenue_nis'],
                row['funding_sources'],
                risk_level,
                classification,
                row['report_url'],
                row['source_links'],
                existing[0],
                row['name_he'],
            ))
            # Update summary only if empty
            if summary:
                unified.execute("""
                    UPDATE organizations SET summary_he = ?
                    WHERE id = ? AND (summary_he IS NULL OR summary_he = '')
                """, (summary, existing[0]))
            updated += 1
        else:
            unified.execute("""
                INSERT OR IGNORE INTO organizations
                (name_he, name_en, org_type, year_founded, registration_number,
                 budget_ils, funding_sources, website, risk_level, classification,
                 summary_he, source_urls)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row['name_he'],
                row['name_en'],
                row['entity_type'],
                row['founded'],
                row['reg'],
                row['revenue_nis'],
                row['funding_sources'],
                row['report_url'],
                risk_level,
                classification,
                summary,
                row['source_links'],
            ))
            count += 1

    src.close()
    print(f"    ({count} new, {updated} updated)")
    return count + updated


def migrate_research_individuals(unified, research_db_path):
    """Migrate individuals from research.db → people table."""
    if not research_db_path:
        return 0

    src = sqlite3.connect(research_db_path)
    src.row_factory = sqlite3.Row

    count = 0
    rows = src.execute("SELECT * FROM individuals").fetchall()

    # Build person→org mapping from org_individuals
    person_orgs = {}
    for link in src.execute("SELECT person_id, org_id, role_type FROM org_individuals").fetchall():
        pid = link['person_id']
        if pid not in person_orgs:
            person_orgs[pid] = []
        person_orgs[pid].append({'org_id': link['org_id'], 'role': link['role_type']})

    # Build person→roles from individual_roles
    person_roles = {}
    for role in src.execute("SELECT * FROM individual_roles").fetchall():
        pid = role['person_id']
        if pid not in person_roles:
            person_roles[pid] = []
        person_roles[pid].append({
            'role': role['role'],
            'org_id': role['org_id'],
            'city': role['city'],
            'government_body': role['government_body'],
        })

    for row in rows:
        pid = row['person_id']
        org_ids = [link['org_id'] for link in person_orgs.get(pid, [])]
        roles = person_roles.get(pid, [])
        primary_role = roles[0]['role'] if roles else None
        city_names = list(set(r['city'] for r in roles if r.get('city')))

        description_parts = []
        if row['political_affiliation']:
            description_parts.append(row['political_affiliation'])
        if row['background']:
            description_parts.append(row['background'])
        description = '; '.join(description_parts) if description_parts else None

        source_urls = row['enrichment_sources'] or row['source']

        # Check if person already exists from reports_metadata key_people
        existing = unified.execute(
            "SELECT id FROM people WHERE name_he=?", (row['name_he'],)
        ).fetchone()

        if existing:
            # Update with richer data
            unified.execute("""
                UPDATE people SET
                    name_en = COALESCE(name_en, ?),
                    role = COALESCE(role, ?),
                    org_ids = COALESCE(?, org_ids),
                    city_names = COALESCE(?, city_names),
                    description = COALESCE(?, description),
                    source_urls = COALESCE(?, source_urls)
                WHERE id = ?
            """, (
                row['name_en'],
                primary_role,
                json.dumps(org_ids) if org_ids else None,
                json.dumps(city_names) if city_names else None,
                description,
                source_urls,
                existing[0],
            ))
        else:
            unified.execute("""
                INSERT OR IGNORE INTO people
                (name_he, name_en, role, org_ids, city_names, description, source_urls)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                row['name_he'],
                row['name_en'],
                primary_role,
                json.dumps(org_ids) if org_ids else None,
                json.dumps(city_names) if city_names else None,
                description,
                source_urls,
            ))
        count += 1

    src.close()
    return count


def migrate_research_programs(unified, research_db_path):
    """Migrate programs from research.db → gefen_programs table + programs table."""
    if not research_db_path:
        return 0, 0

    src = sqlite3.connect(research_db_path)
    src.row_factory = sqlite3.Row

    gefen_count = 0
    prog_count = 0
    rows = src.execute("SELECT * FROM programs").fetchall()

    # Load org_programs links
    org_prog = {}
    for link in src.execute("SELECT org_id, program_id FROM org_programs").fetchall():
        org_prog[link['program_id']] = link['org_id']

    # Load program scores
    prog_scores = {}
    try:
        for s in src.execute("SELECT * FROM analysis_program_scores").fetchall():
            prog_scores[s['program_id']] = s
    except Exception:
        pass

    for row in rows:
        pid = row['program_id']
        score = prog_scores.get(pid)

        # gefen_programs — raw catalog entries
        unified.execute("""
            INSERT OR IGNORE INTO gefen_programs
            (program_name, org_name, gefen_code, description, description_locked,
             description_source, gemini_summary, category, cities, rating)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row['name'],
            row['operator_org_name'],
            row['program_number'],
            row['description'],
            row['description_locked'] or 0,
            'human' if row['description_locked'] else None,
            row['gemini_summary'],
            row['field'],
            row['cities'],
            score['risk_score'] if score else row['original_rating'],
        ))
        gefen_count += 1

        # Also create a programs entry for orgs that have org_programs links
        linked_org_id = org_prog.get(pid)
        if linked_org_id:
            # Find the unified org id by matching research.db org name
            src_org = src.execute("SELECT name_he FROM orgs WHERE org_id=?", (linked_org_id,)).fetchone()
            if src_org:
                unified_org = unified.execute(
                    "SELECT id FROM organizations WHERE name_he=?", (src_org['name_he'],)
                ).fetchone()
                org_id_unified = unified_org[0] if unified_org else None
            else:
                org_id_unified = None

            unified.execute("""
                INSERT OR IGNORE INTO programs
                (name_he, gefen_code, org_id, description, description_auto,
                 gemini_summary, description_locked, domains, rating)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row['name'],
                row['program_number'],
                org_id_unified,
                row['description'] if row['description_locked'] else None,
                row['description_auto'] if not row['description_locked'] else row['description'],
                row['gemini_summary'],
                row['description_locked'] or 0,
                row['field'],
                score['risk_score'] if score else row['original_rating'],
            ))
            prog_count += 1

    src.close()
    return gefen_count, prog_count


def migrate_research_evidence(unified, research_db_path):
    """Migrate evidence from research.db → sources table."""
    if not research_db_path:
        return 0

    src = sqlite3.connect(research_db_path)
    src.row_factory = sqlite3.Row

    count = 0
    rows = src.execute("SELECT * FROM evidence").fetchall()

    for row in rows:
        unified.execute("""
            INSERT OR IGNORE INTO sources
            (url, title, source_type, entity_type, entity_id, notes)
            VALUES (?, ?, 'evidence', ?, ?, ?)
        """, (
            row['source_url'],
            row['source_label'],
            row['entity_type'],
            row['entity_id'],
            json.dumps({
                'layer': row['layer'],
                'text_he': row['text_he'],
                'text_en': row['text_en'],
                'publish_ready': row['publish_ready'],
            }),
        ))
        count += 1

    src.close()
    return count


def migrate_connections(unified, research_db_path):
    """Migrate org_programs, org_cities, org_individuals, org_funding → connections."""
    if not research_db_path:
        return 0

    src = sqlite3.connect(research_db_path)
    src.row_factory = sqlite3.Row

    count = 0

    # org_programs → connections (org runs program)
    for row in src.execute("SELECT * FROM org_programs").fetchall():
        unified.execute("""
            INSERT OR IGNORE INTO connections
            (source_type, source_id, target_type, target_id, relation, evidence)
            VALUES ('org', ?, 'program', ?, 'runs', ?)
        """, (row['org_id'], row['program_id'], row['source']))
        count += 1

    # org_cities → connections (org operates_in city)
    for row in src.execute("SELECT * FROM org_cities").fetchall():
        unified.execute("""
            INSERT OR IGNORE INTO connections
            (source_type, source_id, target_type, target_id, relation, evidence)
            VALUES ('org', ?, 'city', 0, ?, ?)
        """, (
            row['org_id'],
            row['relationship'] or 'operates_in',
            json.dumps({'city_key': row['city_key'], 'source': row['source']}),
        ))
        count += 1

    # org_individuals → connections (org employs/has person)
    for row in src.execute("SELECT * FROM org_individuals").fetchall():
        unified.execute("""
            INSERT OR IGNORE INTO connections
            (source_type, source_id, target_type, target_id, relation, evidence)
            VALUES ('org', ?, 'person', ?, ?, ?)
        """, (
            row['org_id'],
            row['person_id'],
            row['role_type'] or 'member',
            row['source'],
        ))
        count += 1

    # org_funding → connections (funder funds recipient)
    for row in src.execute("SELECT * FROM org_funding").fetchall():
        # Try to find funder org in unified by name
        funder = unified.execute(
            "SELECT id FROM organizations WHERE name_he=?", (row['funder_name'],)
        ).fetchone()
        funder_id = funder[0] if funder else 0

        unified.execute("""
            INSERT OR IGNORE INTO connections
            (source_type, source_id, target_type, target_id, relation, evidence)
            VALUES ('org', ?, 'org', ?, 'funds', ?)
        """, (
            funder_id,
            row['recipient_org_id'],
            json.dumps({
                'funder_name': row['funder_name'],
                'amount_usd': row['amount_usd'],
                'amount_nis': row['amount_nis'],
                'year': row['year'],
                'note': row['note'],
                'source': row['source'],
            }),
        ))
        count += 1

    src.close()
    return count


def migrate_concept_timeline(unified, research_db_path):
    """Migrate concept_adoption_timeline → concepts table."""
    if not research_db_path:
        return 0

    src = sqlite3.connect(research_db_path)
    src.row_factory = sqlite3.Row

    count = 0
    rows = src.execute("SELECT * FROM concept_adoption_timeline").fetchall()

    for row in rows:
        # Insert concept if not exists
        existing = unified.execute(
            "SELECT id FROM concepts WHERE name_he=? AND concept_type='timeline'",
            (row['concept'],)
        ).fetchone()

        if not existing:
            unified.execute("""
                INSERT INTO concepts
                (name_he, concept_type, description, related_org_ids)
                VALUES (?, 'timeline', ?, ?)
            """, (
                row['concept'],
                json.dumps({
                    'entity': row['entity'],
                    'entity_type': row['entity_type'],
                    'first_appearance_year': row['first_appearance_year'],
                    'first_appearance_context': row['first_appearance_context'],
                    'adoption_level': row['adoption_level'],
                    'confidence': row['confidence'],
                    'source': row['source'],
                }),
                None,
            ))
        else:
            # Append as additional timeline entry in description
            old_desc = unified.execute(
                "SELECT description FROM concepts WHERE id=?", (existing[0],)
            ).fetchone()[0]
            entries = []
            if old_desc:
                try:
                    existing_data = json.loads(old_desc)
                    if isinstance(existing_data, list):
                        entries = existing_data
                    else:
                        entries = [existing_data]
                except json.JSONDecodeError:
                    entries = [{'text': old_desc}]
            entries.append({
                'entity': row['entity'],
                'entity_type': row['entity_type'],
                'first_appearance_year': row['first_appearance_year'],
                'first_appearance_context': row['first_appearance_context'],
                'adoption_level': row['adoption_level'],
                'confidence': row['confidence'],
                'source': row['source'],
            })
            unified.execute(
                "UPDATE concepts SET description=? WHERE id=?",
                (json.dumps(entries, ensure_ascii=False), existing[0])
            )
        count += 1

    src.close()
    return count


def migrate_documents(unified, research_db_path):
    """Migrate documents from research.db → sources table."""
    if not research_db_path:
        return 0

    src = sqlite3.connect(research_db_path)
    src.row_factory = sqlite3.Row

    count = 0
    rows = src.execute("SELECT * FROM documents").fetchall()

    for row in rows:
        unified.execute("""
            INSERT OR IGNORE INTO sources
            (url, title, source_type, notes)
            VALUES (?, ?, 'document', ?)
        """, (
            row['url'] or row['file_path'],
            row['title_he'] or row['title_en'],
            json.dumps({
                'doc_type': row['doc_type'],
                'title_en': row['title_en'],
                'title_he': row['title_he'],
                'author': row['author'],
                'year': row['year'],
                'description': row['description'],
                'file_path': row['file_path'],
                'tags': row['tags'],
                'source': row['source'],
            }),
        ))
        count += 1

    # doc_links → connections
    for link in src.execute("SELECT * FROM doc_links").fetchall():
        unified.execute("""
            INSERT OR IGNORE INTO connections
            (source_type, source_id, target_type, target_id, relation)
            VALUES ('document', ?, ?, ?, ?)
        """, (
            link['doc_id'],
            link['entity_type'],
            link['entity_id'],
            link['relationship'] or 'references',
        ))

    src.close()
    return count


def migrate_training_institutions(unified, research_db_path):
    """Migrate training_institutions → organizations table (as training type)."""
    if not research_db_path:
        return 0

    src = sqlite3.connect(research_db_path)
    src.row_factory = sqlite3.Row

    count = 0
    rows = src.execute("SELECT * FROM training_institutions").fetchall()

    for row in rows:
        name = row['institution_name']
        if row['department']:
            name = f"{name} - {row['department']}"

        existing = unified.execute(
            "SELECT id FROM organizations WHERE name_he=?", (name,)
        ).fetchone()

        if not existing:
            unified.execute("""
                INSERT OR IGNORE INTO organizations
                (name_he, org_type, summary_he, website, source_urls)
                VALUES (?, ?, ?, ?, ?)
            """, (
                name,
                row['institution_type'] or 'training',
                json.dumps({
                    'city': row['city'],
                    'type': row['type'],
                    'status': row['status'],
                    'values_statement': row['values_statement'],
                    'placement_pipeline': row['placement_pipeline'],
                    'placement_details': row['placement_details'],
                    'domain': row['domain'],
                    'relation_to_city': row['relation_to_city'],
                }),
                row['source_url'],
                row['source_url'],
            ))
            count += 1

    src.close()
    return count


def migrate_patterns_and_lenses(unified, research_db_path):
    """Migrate patterns + lenses → concepts table."""
    if not research_db_path:
        return 0

    src = sqlite3.connect(research_db_path)
    src.row_factory = sqlite3.Row

    count = 0

    # lenses → concepts
    for row in src.execute("SELECT * FROM lenses").fetchall():
        unified.execute("""
            INSERT OR IGNORE INTO concepts
            (name_he, name_en, concept_type, description, source_urls)
            VALUES (?, ?, 'lens', ?, ?)
        """, (
            row['name_he'],
            row['name_en'],
            json.dumps({
                'domain': row['domain'],
                'description': row['description'],
                'key_concepts': row['key_concepts'],
                'applicable_to': row['applicable_to'],
            }),
            row['source_docs'],
        ))
        count += 1

    # patterns → concepts
    for row in src.execute("SELECT * FROM patterns").fetchall():
        unified.execute("""
            INSERT OR IGNORE INTO concepts
            (name_he, name_en, concept_type, description)
            VALUES (?, ?, 'pattern', ?)
        """, (
            row['name_he'],
            row['name_en'],
            json.dumps({
                'description': row['description'],
                'evidence_summary': row['evidence_summary'],
                'entity_ids': row['entity_ids'],
                'source': row['source'],
                'lens_id': row['lens_id'],
            }),
        ))
        count += 1

    src.close()
    return count


def main():
    dry_run = '--dry-run' in sys.argv

    print("=" * 60)
    print("Unified Research DB Migration")
    print("=" * 60)

    if dry_run:
        print("DRY RUN — no changes will be made\n")

    # Find source databases
    print("\nLocating source databases...")
    research_db = find_db(RESEARCH_DB_PATHS, "research.db")
    reports_meta_db = find_db(REPORTS_META_DB_PATHS, "reports_metadata.db")
    city_matrix_db = find_db(CITY_MATRIX_DB_PATHS, "city_matrix.db")

    if not any([research_db, reports_meta_db, city_matrix_db]):
        print("\nERROR: No source databases found. Aborting.")
        return

    if dry_run:
        print("\nDRY RUN complete. Would migrate from:")
        if research_db: print(f"  - research.db: orgs, individuals, programs, evidence, connections, etc.")
        if reports_meta_db: print(f"  - reports_metadata.db: {reports_meta_db}")
        if city_matrix_db: print(f"  - city_matrix.db: entities, entity_details, city_entity_links")
        return

    if UNIFIED_DB.exists():
        bak = UNIFIED_DB.with_suffix('.db.bak')
        print(f"Backing up existing {UNIFIED_DB.name} → {bak.name} ({UNIFIED_DB.stat().st_size:,} bytes)")
        shutil.copy2(UNIFIED_DB, bak)
        UNIFIED_DB.unlink()

    # Create unified DB with schema
    print(f"\nCreating {UNIFIED_DB}...")
    unified = sqlite3.connect(UNIFIED_DB)

    with open(SCHEMA_SQL) as f:
        unified.executescript(f.read())

    print("Schema created.\n")

    # Run migrations — reports_metadata first (establishes base orgs)
    print("--- 1/9: Migrating reports_metadata ---")
    org_count, report_count = migrate_reports_metadata(unified, reports_meta_db)
    print(f"  → {org_count} organizations, {report_count} reports\n")

    print("--- 2/9: Migrating city_matrix entities ---")
    entity_count = migrate_city_matrix_entities(unified, city_matrix_db)
    print(f"  → {entity_count} entities\n")

    print("--- 3/9: Migrating research files + city markers ---")
    source_count = migrate_research_files(unified, research_db)
    print(f"  → {source_count} sources\n")

    print("--- 4/9: Migrating research orgs (1,598) ---")
    rorg_count = migrate_research_orgs(unified, research_db)
    print(f"  → {rorg_count} orgs total\n")

    print("--- 5/9: Migrating individuals (7,866) ---")
    people_count = migrate_research_individuals(unified, research_db)
    print(f"  → {people_count} people\n")

    print("--- 6/9: Migrating programs (6,065) ---")
    gefen_count, prog_count = migrate_research_programs(unified, research_db)
    print(f"  → {gefen_count} gefen_programs, {prog_count} linked programs\n")

    print("--- 7/9: Migrating evidence (1,560) ---")
    ev_count = migrate_research_evidence(unified, research_db)
    print(f"  → {ev_count} evidence entries\n")

    print("--- 8/9: Migrating connections (org_programs, org_cities, org_individuals, org_funding) ---")
    conn_count = migrate_connections(unified, research_db)
    print(f"  → {conn_count} connections\n")

    print("--- 9/9: Migrating concepts, documents, training, patterns ---")
    concept_count = migrate_concept_timeline(unified, research_db)
    doc_count = migrate_documents(unified, research_db)
    train_count = migrate_training_institutions(unified, research_db)
    pattern_count = migrate_patterns_and_lenses(unified, research_db)
    print(f"  → {concept_count} timeline concepts, {doc_count} documents, {train_count} training institutions, {pattern_count} patterns/lenses\n")

    unified.commit()

    # Print summary
    print("=" * 60)
    print("Migration Summary")
    print("=" * 60)
    tables = unified.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'"
    ).fetchall()
    total = 0
    for (table_name,) in tables:
        count = unified.execute(f"SELECT COUNT(*) FROM [{table_name}]").fetchone()[0]
        print(f"  {table_name}: {count:,} rows")
        total += count

    print(f"\n  TOTAL: {total:,} rows across {len(tables)} tables")
    print(f"\nDatabase size: {UNIFIED_DB.stat().st_size:,} bytes ({UNIFIED_DB.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"Saved to: {UNIFIED_DB}")

    unified.close()


if __name__ == '__main__':
    main()
