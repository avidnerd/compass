-- 003: ephemeral screen monitoring for focus sessions.
-- Raw JPEGs live only in the server's temporary directory and are deleted
-- after analysis. SQLite keeps bounded metadata and the derived evaluation.

ALTER TABLE focus_sessions ADD COLUMN monitoring_enabled INTEGER NOT NULL DEFAULT 0;
ALTER TABLE focus_sessions ADD COLUMN monitoring_status TEXT NOT NULL DEFAULT 'not_started';
ALTER TABLE focus_sessions ADD COLUMN monitoring_surface TEXT;
ALTER TABLE focus_sessions ADD COLUMN monitoring_started_at TEXT;
ALTER TABLE focus_sessions ADD COLUMN monitoring_stopped_at TEXT;
ALTER TABLE focus_sessions ADD COLUMN frames_captured INTEGER NOT NULL DEFAULT 0;
ALTER TABLE focus_sessions ADD COLUMN frames_analyzed INTEGER NOT NULL DEFAULT 0;
ALTER TABLE focus_sessions ADD COLUMN focus_evaluation_json TEXT;
ALTER TABLE focus_sessions ADD COLUMN monitoring_model_id TEXT;

CREATE TABLE focus_frames (
  id TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  session_id TEXT NOT NULL REFERENCES focus_sessions(id) ON DELETE CASCADE,
  captured_at TEXT NOT NULL,
  elapsed_seconds INTEGER NOT NULL,
  width INTEGER NOT NULL,
  height INTEGER NOT NULL,
  byte_size INTEGER NOT NULL,
  storage_path TEXT NOT NULL,
  classification TEXT,
  confidence REAL,
  visible_activity TEXT,
  relevance_reason TEXT,
  contains_sensitive_content INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_focus_frames_session
  ON focus_frames(session_id, elapsed_seconds);
