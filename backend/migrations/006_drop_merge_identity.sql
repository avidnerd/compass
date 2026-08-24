-- 006: drop the Merge Registered User column.
--
-- Compass reads connected accounts only through the user's own Apps Script
-- bridge and a GitHub PAT now (see 005_provider_credentials.sql). The paid
-- connector platform is gone, and with it the per-profile identity it needed.
--
-- The column is UNIQUE, so SQLite cannot ALTER TABLE ... DROP COLUMN it: the
-- table is rebuilt instead. Foreign keys are off for the swap because every
-- other table references profiles(id); they are restored at the end.
PRAGMA foreign_keys=OFF;

BEGIN;

CREATE TABLE profiles_new (
  id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  timezone TEXT NOT NULL DEFAULT 'UTC',
  work_hours_start INTEGER NOT NULL DEFAULT 9,
  work_hours_end INTEGER NOT NULL DEFAULT 18,
  onboarding_step TEXT NOT NULL DEFAULT 'connect',
  share_activity_category INTEGER NOT NULL DEFAULT 0,
  scan_consented INTEGER NOT NULL DEFAULT 0,
  recovery_code_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

INSERT INTO profiles_new
  SELECT id, display_name, timezone, work_hours_start, work_hours_end,
         onboarding_step, share_activity_category, scan_consented,
         recovery_code_hash, created_at, updated_at
  FROM profiles;

DROP TABLE profiles;
ALTER TABLE profiles_new RENAME TO profiles;

COMMIT;

PRAGMA foreign_keys=ON;
