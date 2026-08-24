-- 004: College OS integration.
--
-- College OS (see college-os/) provisions a Google Workspace structure: the
-- COLLEGE Drive tree, the COLLEGE DASHBOARD spreadsheet, five calendars, six
-- Tasks lists, and a Gmail label tree. Compass reads that structure through the
-- same read-only capabilities it already uses.
--
-- Only the LINK (file ids) and the IMPORT LEDGER (which sheet row became which
-- quest) are persisted. Dashboard cell contents are never written to disk —
-- they are fetched uncached and held in process memory only, exactly like the
-- interest-scan excerpts.

CREATE TABLE college_links (
  profile_id TEXT PRIMARY KEY REFERENCES profiles(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'not_detected',   -- not_detected|partial|linked
  root_folder_id TEXT,
  root_folder_name TEXT,
  dashboard_file_id TEXT,
  dashboard_name TEXT,
  dashboard_modified_time TEXT,
  project_home_count INTEGER NOT NULL DEFAULT 0,
  calendars_json TEXT NOT NULL DEFAULT '[]',     -- [{name, id, present}]
  detected_at TEXT,
  last_synced_at TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL
);

-- One row per imported dashboard row. source_key is derived from the row's
-- stable content (tab + area + text hash) so a re-sync never duplicates a quest.
CREATE TABLE college_imports (
  profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  source_key TEXT NOT NULL,
  tab TEXT NOT NULL,                             -- THIS WEEK|SEMESTER GOALS|OPPORTUNITIES
  area TEXT,
  title TEXT NOT NULL,
  quest_id TEXT REFERENCES quests(id) ON DELETE CASCADE,
  imported_at TEXT NOT NULL,
  PRIMARY KEY (profile_id, source_key)
);
CREATE INDEX idx_college_imports_quest ON college_imports(quest_id);
