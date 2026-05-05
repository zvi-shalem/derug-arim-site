# Repo Structure

This repo mixes the public ranking site with research-generation tooling. Keep those layers separate so sessions can load only the context they need.

## Public Site

Files served directly by GitHub Pages stay at the root or under content folders:

- `index.html` - main public ranking page
- `municipal_positions.html` - municipal roles and protocol evidence page
- `research/*.html` - public research pages and dashboards
- `data.js`, `depth_data.js`, `protocol_findings.js`, `protocols_data.js`, `research_data.js`, `research_orgs.js` - browser data bundles

## Research Pipeline

Generation and cleanup tools live under `scripts/research_pipeline/`:

- `migrate_to_unified.py` - builds `research_unified.db` from source databases
- `add_sources.py` - adds source URLs to municipal role records
- `clean_positions.py` - cleans role strings and training tags
- `replace_protocols.py` - injects structured protocol findings
- `rebuild_positions.py` - rebuilds `municipal_positions.html`
- `save_metadata.py` - writes metadata into `research/reports_metadata.db`

Shared SQL schemas live under `data/schemas/`.

## Working Notes

Non-public work products live under `docs/research_worklog/`. These are useful for audit and handoff, but should not be treated as the canonical source for the public site.

## Local Artifacts

SQLite databases, WAL/SHM files, backups, screenshots, and temporary broken-page copies are ignored by git. Store old local DB backups under `db_backups/` and manual HTML snapshots under `archive/manual_page_versions/`.

Do not commit:

- `*.db`, `*.db-shm`, `*.db-wal`
- `*.db.backup_*`, `*.db.bak*`
- `*.bak`, `*_broken.html`, `*_pre_enrichment.html`

