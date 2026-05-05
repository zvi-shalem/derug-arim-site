# Preservation Status - 2026-05-05 08:35

Purpose: record the current preservation state after organizing the research-site repo, so project context and generated artifacts are not lost.

## Git Checkpoints

- `c51db9b` - `Organize research pipeline files`
- `f27ff62` - `Capture municipal positions and research pages`

`git status --short` was clean after `c51db9b`.

## Tracked Content

The following categories are preserved in git:

- Public pages: root HTML/JS files and `research/*.html`
- Research pipeline scripts: `scripts/research_pipeline/`
- SQL schemas: `data/schemas/`
- Worklog notes: `docs/research_worklog/`
- Repo structure documentation: `docs/REPO_STRUCTURE.md`

## Local Artifacts Kept Outside Git

Large or transient artifacts were not deleted. They remain local and ignored by git:

- Active DB: `research_unified.db`
- Immediate DB backup: `research_unified.db.bak`
- DB backups moved to: `db_backups/`
- Manual HTML snapshots moved to: `archive/manual_page_versions/`
- SQLite transient files: `research_unified.db-shm`, `research_unified.db-wal`

## Safety Note

During verification, `migrate_to_unified.py --dry-run` exposed a bug where backup/delete logic ran before the dry-run exit. The active DB was restored from `research_unified.db.bak`, and the script was fixed so dry-run mode only discovers and reports sources.

