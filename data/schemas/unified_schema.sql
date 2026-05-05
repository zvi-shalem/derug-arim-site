-- unified research database schema
-- created: 2026-03-25
-- purpose: single source of truth for דירוג ערים research data

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- 1. organizations — all researched orgs, NGOs, government bodies
CREATE TABLE IF NOT EXISTS organizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name_he TEXT NOT NULL,
    name_en TEXT,
    org_type TEXT,                    -- עמותה/חברה/ממשלתי/בינלאומי/אקדמי/ספק עצמאי/רעיון
    year_founded INTEGER,
    registration_number TEXT,         -- ח"פ
    budget_ils TEXT,                  -- text for ranges like "50M-100M" or "כ-3.8 מיליון ש"ח"
    funding_sources TEXT,             -- JSON array
    website TEXT,
    risk_level TEXT,                  -- high/medium/low/unknown
    classification TEXT,              -- ideological classification badge text
    summary_he TEXT,
    source_urls TEXT,                 -- JSON array of source URLs
    report_filename TEXT,             -- link to deep_*.html report (e.g. "deep_ACRI")
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_org_name ON organizations(name_he);
CREATE INDEX IF NOT EXISTS idx_org_type ON organizations(org_type);
CREATE INDEX IF NOT EXISTS idx_org_risk ON organizations(risk_level);
CREATE INDEX IF NOT EXISTS idx_org_report ON organizations(report_filename);

-- 2. people — key individuals (activists, directors, academics, politicians)
CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name_he TEXT NOT NULL,
    name_en TEXT,
    role TEXT,
    org_ids TEXT,                     -- JSON array of org IDs
    city_names TEXT,                  -- JSON array
    description TEXT,
    source_urls TEXT,                 -- JSON array
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_people_name ON people(name_he);

-- 3. programs — educational programs (Gefen and others)
CREATE TABLE IF NOT EXISTS programs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name_he TEXT NOT NULL,
    name_en TEXT,
    gefen_code TEXT,                  -- גפ"ן code if applicable
    org_id INTEGER REFERENCES organizations(id),
    description TEXT,                 -- human description — SACRED, never overwrite programmatically
    description_auto TEXT,
    gemini_summary TEXT,
    description_locked INTEGER DEFAULT 0,
    domains TEXT,                     -- JSON array
    target_ages TEXT,
    city_names TEXT,                  -- JSON array of cities where deployed
    rating REAL,
    source_urls TEXT,                 -- JSON array
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_prog_org ON programs(org_id);
CREATE INDEX IF NOT EXISTS idx_prog_gefen ON programs(gefen_code);

-- 4. concepts — methodologies, ideological frameworks, terms
CREATE TABLE IF NOT EXISTS concepts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name_he TEXT NOT NULL,
    name_en TEXT,
    concept_type TEXT,               -- methodology/ideology/framework/term
    description TEXT,
    related_org_ids TEXT,            -- JSON array
    source_urls TEXT,                -- JSON array
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_concept_type ON concepts(concept_type);

-- 5. connections — relationships between any entities
CREATE TABLE IF NOT EXISTS connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,        -- org/person/program/concept
    source_id INTEGER NOT NULL,
    target_type TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    relation TEXT NOT NULL,           -- funds/employs/runs/founded_by/partner/advisor/board_member/etc
    evidence TEXT,
    source_url TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_conn_source ON connections(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_conn_target ON connections(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_conn_relation ON connections(relation);

-- 6. sources — all referenced URLs and documents
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT,
    title TEXT,
    source_type TEXT,                -- website/document/video/protocol/news/database
    entity_type TEXT,                -- org/person/program/concept
    entity_id INTEGER,
    accessed_date TEXT,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_source_entity ON sources(entity_type, entity_id);

-- 7. reports — deep research report files
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT UNIQUE NOT NULL,   -- deep_ACRI etc (without _he suffix or .html extension)
    name_he TEXT,
    name_en TEXT,
    org_id INTEGER REFERENCES organizations(id),
    translated INTEGER DEFAULT 0,    -- 1 if _he.html exists
    file_size_bytes INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_report_filename ON reports(filename);

-- 8. gefen_programs — raw Gefen catalog entries (6064 programs)
CREATE TABLE IF NOT EXISTS gefen_programs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    program_name TEXT,
    org_name TEXT,
    gefen_code TEXT,
    description TEXT,
    description_locked INTEGER DEFAULT 0,
    description_source TEXT,
    gemini_summary TEXT,
    category TEXT,
    cities TEXT,                      -- JSON array
    rating REAL,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_gefen_code ON gefen_programs(gefen_code);
CREATE INDEX IF NOT EXISTS idx_gefen_org ON gefen_programs(org_name);
