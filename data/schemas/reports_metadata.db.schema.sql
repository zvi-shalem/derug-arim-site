CREATE TABLE IF NOT EXISTS reports_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT UNIQUE NOT NULL,          -- e.g. "deep_ACRI"
    name_he TEXT,                           -- Hebrew name of org/person
    name_en TEXT,                           -- English name
    org_type TEXT,                          -- organization/person/program/concept
    year_founded INTEGER,                   -- founding year
    budget_ils TEXT,                        -- budget in ILS (text for ranges like "50M-100M")
    connected_orgs TEXT,                    -- JSON array of connected org names
    connected_cities TEXT,                  -- JSON array of city names
    domains TEXT,                           -- JSON array: education/gender/culture/language/etc
    key_people TEXT,                        -- JSON array of key people names
    funding_sources TEXT,                   -- JSON array of funding sources
    risk_level TEXT,                        -- high/medium/low (from original report)
    summary_he TEXT,                        -- 1-2 sentence Hebrew summary
    translated INTEGER DEFAULT 0,          -- 1 if _he.html exists
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_reports_cities ON reports_metadata(connected_cities);
CREATE INDEX IF NOT EXISTS idx_reports_orgs ON reports_metadata(connected_orgs);
CREATE INDEX IF NOT EXISTS idx_reports_type ON reports_metadata(org_type);
