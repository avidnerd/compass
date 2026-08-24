-- 001: full initial schema for Compass.
-- The legacy unscoped prototype cache is deliberately NOT imported: it cannot
-- be attributed to individual profiles.

CREATE TABLE profiles (
  id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  timezone TEXT NOT NULL DEFAULT 'UTC',
  work_hours_start INTEGER NOT NULL DEFAULT 9,
  work_hours_end INTEGER NOT NULL DEFAULT 18,
  merge_registered_user_id TEXT UNIQUE,
  onboarding_step TEXT NOT NULL DEFAULT 'connect',
  share_activity_category INTEGER NOT NULL DEFAULT 0,
  scan_consented INTEGER NOT NULL DEFAULT 0,
  recovery_code_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE auth_sessions (
  id TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  expires_at TEXT NOT NULL,
  last_used_at TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE connector_states (
  profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  connector TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'unknown',      -- unknown|connected|disconnected|unsupported|degraded|error
  capabilities_json TEXT NOT NULL DEFAULT '[]',
  last_checked_at TEXT,
  error_code TEXT,
  generation INTEGER NOT NULL DEFAULT 0,
  last_manual_refresh_at TEXT,
  PRIMARY KEY (profile_id, connector)
);

CREATE TABLE interest_profiles (
  profile_id TEXT PRIMARY KEY REFERENCES profiles(id) ON DELETE CASCADE,
  topics_json TEXT NOT NULL DEFAULT '[]',
  palette TEXT,
  motif TEXT,
  accessories_json TEXT NOT NULL DEFAULT '[]',
  props_json TEXT NOT NULL DEFAULT '[]',
  personality_presets_json TEXT NOT NULL DEFAULT '[]',
  name_suggestions_json TEXT NOT NULL DEFAULT '[]',
  tone TEXT,
  confidence REAL,
  explanation TEXT,
  source_fingerprint TEXT,
  model_id TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL
);

CREATE TABLE source_summaries (
  profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  file_id TEXT NOT NULL,
  connector TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  labels_json TEXT NOT NULL DEFAULT '[]',
  modified_time TEXT,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (profile_id, file_id)
);

CREATE TABLE characters (
  profile_id TEXT PRIMARY KEY REFERENCES profiles(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  pronouns TEXT NOT NULL DEFAULT 'they/them',
  species TEXT NOT NULL,
  palette TEXT NOT NULL,
  eyes TEXT NOT NULL DEFAULT 'round',
  markings TEXT NOT NULL DEFAULT 'none',
  accessory TEXT NOT NULL DEFAULT 'none',
  aura TEXT NOT NULL DEFAULT 'none',
  habitat TEXT NOT NULL DEFAULT 'meadow',
  props_json TEXT NOT NULL DEFAULT '[]',
  personality TEXT NOT NULL DEFAULT 'cheerful',
  voice_tone TEXT NOT NULL DEFAULT 'warm',
  xp INTEGER NOT NULL DEFAULT 0,
  level INTEGER NOT NULL DEFAULT 1,
  care_points INTEGER NOT NULL DEFAULT 3,
  energy INTEGER NOT NULL DEFAULT 80,
  mood INTEGER NOT NULL DEFAULT 70,
  bond INTEGER NOT NULL DEFAULT 0,
  stat_focus INTEGER NOT NULL DEFAULT 1,
  stat_curiosity INTEGER NOT NULL DEFAULT 1,
  stat_craft INTEGER NOT NULL DEFAULT 1,
  stat_communication INTEGER NOT NULL DEFAULT 1,
  stat_collaboration INTEGER NOT NULL DEFAULT 1,
  stat_balance INTEGER NOT NULL DEFAULT 1,
  expression TEXT NOT NULL DEFAULT 'content',
  animation TEXT NOT NULL DEFAULT 'idle',
  evolution_stage INTEGER NOT NULL DEFAULT 0,
  unlocks_json TEXT NOT NULL DEFAULT '[]',
  last_play_bond_date TEXT,
  last_coop_collab_date TEXT,
  needs_updated_at TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE character_memories (
  id TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  kind TEXT NOT NULL DEFAULT 'reflection',     -- reflection|encourage|postcard|boss|battle
  text TEXT NOT NULL,
  visibility TEXT NOT NULL DEFAULT 'private',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_memories_profile ON character_memories(profile_id, created_at DESC);

CREATE TABLE quests (
  id TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  goal TEXT NOT NULL,
  meaning TEXT,
  state TEXT NOT NULL DEFAULT 'draft',         -- draft|planning|active|completed|archived
  target_date TEXT,
  session_length_minutes INTEGER NOT NULL DEFAULT 25,
  share_category INTEGER NOT NULL DEFAULT 0,
  category TEXT NOT NULL DEFAULT 'general',
  targets_json TEXT NOT NULL DEFAULT '{}',
  plan_model_id TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_quests_profile ON quests(profile_id, created_at DESC);

CREATE TABLE subgoals (
  id TEXT PRIMARY KEY,
  quest_id TEXT NOT NULL REFERENCES quests(id) ON DELETE CASCADE,
  profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  position INTEGER NOT NULL DEFAULT 0,
  title TEXT NOT NULL,
  rationale TEXT,
  acceptance_criterion TEXT NOT NULL,
  difficulty INTEGER NOT NULL DEFAULT 2,
  estimated_sessions INTEGER NOT NULL DEFAULT 1,
  state TEXT NOT NULL DEFAULT 'todo',          -- todo|in_progress|verifying|needs_confirmation|completed
  evidence_specs_json TEXT NOT NULL DEFAULT '[]',
  manual_fallback TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_subgoals_quest ON subgoals(quest_id, position);

CREATE TABLE focus_sessions (
  id TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  quest_id TEXT REFERENCES quests(id) ON DELETE SET NULL,
  subgoal_id TEXT REFERENCES subgoals(id) ON DELETE SET NULL,
  battle_id TEXT,
  state TEXT NOT NULL DEFAULT 'running',       -- running|paused|ending|completed|canceled
  planned_seconds INTEGER NOT NULL,
  started_at TEXT NOT NULL,
  paused_at TEXT,
  paused_total_seconds INTEGER NOT NULL DEFAULT 0,
  finished_at TEXT,
  focus_score INTEGER,
  demo INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX idx_one_active_session
  ON focus_sessions(profile_id) WHERE state IN ('running','paused','ending');
CREATE INDEX idx_sessions_profile ON focus_sessions(profile_id, created_at DESC);

CREATE TABLE telemetry_snapshots (
  id TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  session_id TEXT REFERENCES focus_sessions(id) ON DELETE CASCADE,
  phase TEXT NOT NULL,                         -- baseline|final|scan
  metrics_json TEXT NOT NULL DEFAULT '{}',
  generations_json TEXT NOT NULL DEFAULT '{}',
  captured_at TEXT NOT NULL
);
CREATE INDEX idx_snapshots_session ON telemetry_snapshots(session_id);

CREATE TABLE evidence_items (
  id TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  session_id TEXT NOT NULL REFERENCES focus_sessions(id) ON DELETE CASCADE,
  source TEXT NOT NULL,
  event_type TEXT NOT NULL,
  occurred_at TEXT,
  external_ref_hash TEXT,
  content_hash TEXT,
  summary TEXT NOT NULL,
  metric_delta_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE INDEX idx_evidence_session ON evidence_items(session_id);

CREATE TABLE verifications (
  id TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  session_id TEXT NOT NULL UNIQUE REFERENCES focus_sessions(id) ON DELETE CASCADE,
  subgoal_id TEXT REFERENCES subgoals(id) ON DELETE SET NULL,
  result TEXT NOT NULL,                        -- verified|not_completed|needs_confirmation
  confidence REAL NOT NULL DEFAULT 0,
  explanation TEXT NOT NULL DEFAULT '',
  observed TEXT NOT NULL DEFAULT '',
  not_observed TEXT NOT NULL DEFAULT '',
  sources_json TEXT NOT NULL DEFAULT '[]',
  model_id TEXT,
  human_confirmed INTEGER,                     -- NULL=pending, 1=yes, 0=rejected
  last_recheck_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE stat_ledger (
  id TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  source_event_key TEXT NOT NULL UNIQUE,
  xp INTEGER NOT NULL DEFAULT 0,
  care_points INTEGER NOT NULL DEFAULT 0,
  stats_json TEXT NOT NULL DEFAULT '{}',
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_ledger_profile ON stat_ledger(profile_id, created_at DESC);

CREATE TABLE battles (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  host_profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  duration_seconds INTEGER NOT NULL,
  state TEXT NOT NULL DEFAULT 'waiting',       -- waiting|countdown|active|resolving|completed|canceled
  countdown_at TEXT,
  started_at TEXT,
  ends_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE battle_players (
  battle_id TEXT NOT NULL REFERENCES battles(id) ON DELETE CASCADE,
  profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  display_name TEXT NOT NULL,
  ready INTEGER NOT NULL DEFAULT 0,
  subgoal_id TEXT,
  session_id TEXT,
  power INTEGER,
  placement INTEGER,
  left_at TEXT,
  joined_at TEXT NOT NULL,
  PRIMARY KEY (battle_id, profile_id)
);

CREATE TABLE parties (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  theme TEXT NOT NULL DEFAULT 'aurora',
  owner_profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL
);

CREATE TABLE party_members (
  party_id TEXT NOT NULL REFERENCES parties(id) ON DELETE CASCADE,
  profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  joined_at TEXT NOT NULL,
  PRIMARY KEY (party_id, profile_id)
);

CREATE TABLE boss_encounters (
  id TEXT PRIMARY KEY,
  party_id TEXT NOT NULL REFERENCES parties(id) ON DELETE CASCADE,
  difficulty TEXT NOT NULL DEFAULT 'standard', -- easy|standard|epic
  hp_max INTEGER NOT NULL,
  hp_current INTEGER NOT NULL,
  state TEXT NOT NULL DEFAULT 'active',        -- active|defeated|expired
  theme_json TEXT NOT NULL DEFAULT '{}',
  started_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  resolved_at TEXT
);
CREATE INDEX idx_boss_party ON boss_encounters(party_id, started_at DESC);

CREATE TABLE boss_contributions (
  id TEXT PRIMARY KEY,
  encounter_id TEXT NOT NULL REFERENCES boss_encounters(id) ON DELETE CASCADE,
  profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  session_id TEXT NOT NULL UNIQUE,
  damage INTEGER NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE game_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  audience_type TEXT NOT NULL,                 -- profile|battle|party
  audience_id TEXT NOT NULL,
  type TEXT NOT NULL,
  aggregate_id TEXT,
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE INDEX idx_events_audience ON game_events(audience_type, audience_id, id);

CREATE TABLE jobs (
  id TEXT PRIMARY KEY,
  profile_id TEXT REFERENCES profiles(id) ON DELETE CASCADE,
  type TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'queued',        -- queued|running|succeeded|failed|canceled
  progress REAL NOT NULL DEFAULT 0,
  error_code TEXT,
  retry_count INTEGER NOT NULL DEFAULT 0,
  payload_json TEXT NOT NULL DEFAULT '{}',
  result_type TEXT,
  result_id TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_jobs_state ON jobs(state, created_at);
CREATE INDEX idx_jobs_profile ON jobs(profile_id, created_at DESC);

CREATE TABLE idempotency_records (
  profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  idem_key TEXT NOT NULL,
  endpoint TEXT NOT NULL,
  response_json TEXT NOT NULL,
  status_code INTEGER NOT NULL DEFAULT 200,
  created_at TEXT NOT NULL,
  PRIMARY KEY (profile_id, endpoint, idem_key)
);

-- Provider tool cache. scope_id is the profile id (or 'global' for the shared
-- provider tool list / OpenRouter catalog). Raw scanned excerpts must NEVER be
-- written here.
CREATE TABLE tool_cache (
  cache_key TEXT PRIMARY KEY,
  scope_id TEXT NOT NULL,
  connector TEXT NOT NULL,
  capability TEXT NOT NULL,
  args_json TEXT NOT NULL,
  response_json TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  hit_count INTEGER NOT NULL DEFAULT 0,
  stale_hits INTEGER NOT NULL DEFAULT 0,
  last_hit_at TEXT
);
CREATE INDEX idx_tool_cache_scope ON tool_cache(scope_id, connector);

CREATE TABLE analytics_cache (
  cache_key TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL,
  metric_name TEXT NOT NULL,
  params_json TEXT NOT NULL,
  result_json TEXT NOT NULL,
  computed_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  hit_count INTEGER NOT NULL DEFAULT 0,
  stale_hits INTEGER NOT NULL DEFAULT 0,
  last_hit_at TEXT
);
CREATE INDEX idx_analytics_cache_profile ON analytics_cache(profile_id);

CREATE TABLE llm_cache (
  cache_key TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL,
  purpose TEXT NOT NULL,
  model_id TEXT NOT NULL,
  result_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT                              -- NULL = immutable
);
CREATE INDEX idx_llm_cache_profile ON llm_cache(profile_id);

CREATE TABLE cache_counters (
  scope_id TEXT NOT NULL,
  counter TEXT NOT NULL,                       -- hits|misses|stale_serves|avoided_calls
  value INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (scope_id, counter)
);
