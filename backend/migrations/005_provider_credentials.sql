-- 005: pluggable data-plane providers.
--
-- Compass reads connected data through the College OS Apps Script bridge the
-- user deploys in their own Google account, plus a GitHub personal access
-- token. Those credentials live here, per profile.
--
-- These are secrets: no endpoint may echo config_json back to the client. The
-- API returns only whether a provider is configured plus a masked hint.

CREATE TABLE provider_credentials (
  profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  provider TEXT NOT NULL,                    -- bridge|github
  config_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'unknown',    -- unknown|ok|error
  error_code TEXT,
  last_checked_at TEXT,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (profile_id, provider)
);
