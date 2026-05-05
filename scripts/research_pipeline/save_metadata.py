#!/usr/bin/env python3
"""Save report metadata to reports_metadata.db. Used by translation workers."""
import sqlite3, json, sys, os, argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / 'research/reports_metadata.db'

def save(filename, name_he, name_en, org_type, year_founded=None, budget_ils=None,
         connected_orgs=None, connected_cities=None, domains=None, key_people=None,
         funding_sources=None, risk_level=None, summary_he=None, translated=0):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""INSERT OR REPLACE INTO reports_metadata
        (filename, name_he, name_en, org_type, year_founded, budget_ils,
         connected_orgs, connected_cities, domains, key_people,
         funding_sources, risk_level, summary_he, translated)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (filename, name_he, name_en, org_type, year_founded, budget_ils,
         json.dumps(connected_orgs or [], ensure_ascii=False),
         json.dumps(connected_cities or [], ensure_ascii=False),
         json.dumps(domains or [], ensure_ascii=False),
         json.dumps(key_people or [], ensure_ascii=False),
         json.dumps(funding_sources or [], ensure_ascii=False),
         risk_level, summary_he, translated))
    conn.commit()
    conn.close()
    print(f"Saved metadata for {filename}")

def list_all():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT filename, name_he, translated FROM reports_metadata ORDER BY filename").fetchall()
    conn.close()
    for r in rows:
        status = "✓" if r[2] else "○"
        print(f"  {status} {r[0]} — {r[1]}")
    print(f"\nTotal: {len(rows)} ({sum(1 for r in rows if r[2])} translated)")

def stats():
    conn = sqlite3.connect(DB_PATH)
    total = conn.execute("SELECT COUNT(*) FROM reports_metadata").fetchone()[0]
    translated = conn.execute("SELECT COUNT(*) FROM reports_metadata WHERE translated=1").fetchone()[0]
    conn.close()
    print(f"Total: {total}, Translated: {translated}, Remaining: {total - translated}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='cmd')
    sub.add_parser('list')
    sub.add_parser('stats')
    s = sub.add_parser('save')
    s.add_argument('--filename', required=True)
    s.add_argument('--name-he', required=True)
    s.add_argument('--name-en', required=True)
    s.add_argument('--org-type', required=True)
    s.add_argument('--year-founded', type=int)
    s.add_argument('--budget-ils')
    s.add_argument('--connected-orgs', help='JSON array')
    s.add_argument('--connected-cities', help='JSON array')
    s.add_argument('--domains', help='JSON array')
    s.add_argument('--key-people', help='JSON array')
    s.add_argument('--funding-sources', help='JSON array')
    s.add_argument('--risk-level')
    s.add_argument('--summary-he')
    s.add_argument('--translated', type=int, default=0)
    args = parser.parse_args()
    if args.cmd == 'list':
        list_all()
    elif args.cmd == 'stats':
        stats()
    elif args.cmd == 'save':
        save(args.filename, args.name_he, args.name_en, args.org_type,
             args.year_founded, args.budget_ils,
             json.loads(args.connected_orgs) if args.connected_orgs else None,
             json.loads(args.connected_cities) if args.connected_cities else None,
             json.loads(args.domains) if args.domains else None,
             json.loads(args.key_people) if args.key_people else None,
             json.loads(args.funding_sources) if args.funding_sources else None,
             args.risk_level, args.summary_he, args.translated)
