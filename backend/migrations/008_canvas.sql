-- Canvas assignments imported as quests, tracked so an import is idempotent.
--
-- The feed URL itself is NOT stored here: it is a bearer secret and lives in
-- provider_credentials, encrypted with COMPASS_APP_SECRET like every other
-- provider credential.
--
-- source_key is the Canvas VEVENT UID, which is stable across feed refreshes,
-- so re-importing the same assignment updates the row instead of creating a
-- second quest.

CREATE TABLE canvas_imports (
  profile_id  TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  source_key  TEXT NOT NULL,            -- Canvas VEVENT UID
  title       TEXT NOT NULL,
  course      TEXT,
  due_at      TEXT,
  quest_id    TEXT REFERENCES quests(id) ON DELETE SET NULL,
  imported_at TEXT NOT NULL,
  PRIMARY KEY (profile_id, source_key)
);

CREATE INDEX idx_canvas_imports_quest ON canvas_imports(quest_id);
