export interface Profile {
  id: string
  display_name: string
  timezone: string
  work_hours_start: number
  work_hours_end: number
  onboarding_step: 'connect' | 'scan' | 'companion' | 'quest' | 'done'
  share_activity_category: boolean
  scan_consented: boolean
  created_at: string
}

export interface ConnectorState {
  connector: string
  status: string
  error_code: string | null
  capabilities: string[]
  last_checked_at: string | null
  generation?: number
}

export interface InterestTopic {
  label: string
  confidence: number
}

export interface InterestProfile {
  topics: InterestTopic[]
  palette: string | null
  motif: string | null
  accessories: string[]
  props: string[]
  personality_presets: string[]
  name_suggestions: string[]
  tone: string | null
  confidence: number | null
  explanation: string | null
  model_id: string | null
  version: number
  updated_at: string
}

export interface Character {
  profile_id: string
  name: string
  pronouns: string
  species: string
  palette: string
  eyes: string
  markings: string
  accessory: string
  aura: string
  habitat: string
  props: string[]
  personality: string
  voice_tone: string
  xp: number
  level: number
  care_points: number
  energy: number
  mood: number
  bond: number
  stat_focus: number
  stat_curiosity: number
  stat_craft: number
  stat_communication: number
  stat_collaboration: number
  stat_balance: number
  expression: string
  animation: string
  evolution_stage: number
  unlocks: string[]
  version: number
}

export interface Memory {
  id: string
  kind: string
  text: string
  visibility: string
  created_at: string
}

export interface Subgoal {
  id: string
  position: number
  title: string
  rationale: string | null
  acceptance_criterion: string
  difficulty: number
  estimated_sessions: number
  state: 'todo' | 'in_progress' | 'verifying' | 'needs_confirmation' | 'completed'
  evidence_specs: string[]
  manual_fallback: string | null
}

export interface Quest {
  id: string
  goal: string
  meaning: string | null
  state: 'draft' | 'planning' | 'active' | 'completed' | 'archived'
  target_date: string | null
  session_length_minutes: number
  share_category: boolean | number
  category: string
  plan_model_id: string | null
  version: number
  created_at: string
  subgoals?: Subgoal[]
  subgoal_total?: number
  subgoal_done?: number
}

export interface FocusSession {
  id: string
  quest_id: string | null
  subgoal_id: string | null
  state: 'running' | 'paused' | 'ending' | 'completed' | 'canceled'
  planned_seconds: number
  started_at: string
  paused_at: string | null
  paused_total_seconds: number
  finished_at: string | null
  focus_score: number | null
  demo: boolean
  monitoring_enabled: boolean
  monitoring_status: 'not_started' | 'active' | 'paused' | 'stopped' | 'completed' | 'canceled' | 'unavailable'
  monitoring_surface: 'monitor' | 'window' | 'browser' | 'unknown' | null
  monitoring_started_at: string | null
  monitoring_stopped_at: string | null
  monitoring_interval_seconds: number
  frames_captured: number
  frames_analyzed: number
  monitoring_model_id: string | null
  focus_evaluation: FocusEvaluation | null
  server_time: string
  created_at: string
}

export type FocusClassification = 'direct_work' | 'supporting_work' | 'off_task' | 'unclear'

export interface FocusTimelineSegment {
  started_at_seconds: number
  ended_at_seconds: number
  duration_seconds: number
  classification: FocusClassification
  confidence: number
  visible_activity: string
  has_evidence: boolean
}

export interface FocusEvaluation {
  status: 'analyzed' | 'analysis_unavailable' | 'not_monitored'
  model_id: string | null
  frames_captured: number
  frames_analyzed: number
  timing: {
    total_session_seconds: number
    captured_seconds: number
    paused_seconds: number
    unmonitored_seconds: number
  }
  attention: {
    direct_work_seconds: number
    supporting_work_seconds: number
    off_task_seconds: number
    unclear_seconds: number
    focused_percentage: number
    direct_work_percentage: number
  }
  continuity: {
    longest_uninterrupted_seconds: number
    average_uninterrupted_seconds: number
    focus_streak_count: number
  }
  recovery: {
    distraction_episodes: number
    recovered_episodes: number
    average_recovery_seconds: number | null
    longest_distraction_seconds: number
  }
  confidence: {
    overall: number
    screenshot_coverage: number
    unclear_percentage: number
  }
  summary: {
    headline: string
    strength: string
    friction: string
    next_session_recommendation: string
  }
  timeline: FocusTimelineSegment[]
}

export interface EvidenceItem {
  id: string
  source: string
  event_type: string
  occurred_at: string | null
  summary: string
  debug_excerpt?: string | null
}

export interface Verification {
  id: string
  session_id: string
  result: 'verified' | 'not_completed' | 'needs_confirmation'
  confidence: number
  explanation: string
  observed: string
  not_observed: string
  sources: string[]
  model_id: string | null
  human_confirmed: number | null
  evidence: EvidenceItem[]
}

export interface Job {
  id: string
  type: string
  state: 'queued' | 'running' | 'succeeded' | 'failed' | 'canceled'
  progress: number
  error_code: string | null
  result_type: string | null
  result_id: string | null
}

export interface Party {
  id: string
  code: string
  name: string
  theme: string
  owner_profile_id: string
  members: {
    profile_id: string
    display_name: string
    joined_at: string
    is_simulated?: boolean
    avatar?: string
    status?: SimulatedPlayerStatus
    title?: string
    companion_name?: string
  }[]
  created_at: string
}

export type SimulatedPlayerStatus = 'online' | 'in_focus' | 'away'

export interface SimulatedPlayerStats {
  focus_minutes: number
  focus_streak: number
  quests_completed: number
  collaboration: number
}

export interface SimulatedPlayer {
  id: string
  display_name: string
  handle: string
  avatar: string
  title: string
  status: SimulatedPlayerStatus
  availability: string
  companion_name: string
  companion_species: string
  level: number
  palette: string
  personality: string
  stats: SimulatedPlayerStats
}

export interface FreeModelStatus {
  configured: boolean
  models: { id: string; status: string }[]
  selected_model: string | null
  scan_model: { id: string; status: string } | null
  available: boolean
  auth_state: 'unknown' | 'ok' | 'failed'
}

export interface GameEvent {
  id: number
  type: string
  aggregate_id: string | null
  payload: Record<string, unknown>
  created_at: string
}

// ------------------------------------------------------------- College OS

export interface CollegeLink {
  status: 'not_detected' | 'partial' | 'linked'
  root_folder_id: string | null
  root_folder_name: string | null
  dashboard_file_id: string | null
  dashboard_name: string | null
  dashboard_modified_time: string | null
  project_home_count: number
  calendars: { name: string; present: boolean }[]
  detected_at: string | null
  last_synced_at: string | null
}

export interface CollegeThisWeek {
  areas: {
    area: string
    goal: string
    definition_of_done: string
    progress: string
    evidence: string
    source_key: string
  }[]
  big_three: { text: string; source_key: string }[]
  not_this_week: string[]
}

export interface CollegeSemesterGoal {
  area: string
  outcome: string
  metric: string
  status: string
  source_key: string
}

export interface CollegeOpportunity {
  title: string
  type: string
  deadline: string
  value: string
  probability: string
  next_action: string
  status: string
  open: boolean
  source_key: string
}

export interface CollegeReviews {
  entries: {
    week_of: string
    goal: string
    result: string
    completed: string
    evidence: string
    why: string
    failure_type: string
    change_next_week: string
  }[]
  total: number
  outcomes: Record<string, number>
  failure_types: Record<string, number>
  evidence_rate: number | null
  dominant_failure: string | null
}

export interface CollegeTimeLog {
  samples: number
  multipliers: { category: string; multiplier: number; samples: number; confident: boolean }[]
  overall_multiplier: number | null
  min_samples: number
}

export interface CollegeDashboard {
  sections: {
    'THIS WEEK'?: CollegeThisWeek
    'SEMESTER GOALS'?: CollegeSemesterGoal[]
    OPPORTUNITIES?: CollegeOpportunity[]
    'WEEKLY REVIEWS'?: CollegeReviews
    'TIME LOG'?: CollegeTimeLog
  }
  missing_tabs: string[]
  dashboard_file_id: string
  read_at: string
}

export interface CollegeImportable {
  source_key: string
  tab: string
  area: string
  title: string
  meaning: string
  acceptance_criterion: string
  target_date: string | null
  evidence_specs: string[]
  imported_quest_id: string | null
  quest_state: string | null
}

export interface CollegeOverview {
  link: CollegeLink
  dashboard: CollegeDashboard | null
  importable: CollegeImportable[]
  imports: {
    source_key: string
    tab: string
    area: string
    title: string
    quest_id: string
    quest_state: string | null
    imported_at: string
  }[]
  available_evidence_types?: string[]
  rhythms?: string[]
  task_lists?: string[]
  hint?: string
}

export interface CollegeImportResult {
  created: { source_key: string; quest_id: string; goal: string }[]
  skipped: { source_key: string; quest_id: string }[]
  unknown: string[]
}

// ------------------------------------------------------- data providers

export interface ProviderSlot {
  configured: boolean
  from_env: boolean
  token_hint: string | null
  status: 'unknown' | 'ok' | 'error'
  error_code: string | null
  last_checked_at?: string | null
}

export interface ProviderState {
  active: 'bridge' | null
  bridge: ProviderSlot
  github: ProviderSlot
  handshake?: { ok: boolean; capabilities: string[]; timezone: string | null }
}

export interface CanvasLink {
  status: 'linked' | 'not_linked'
  feed: string | null
  connection_status?: string
  error_code?: string | null
  last_checked_at?: string | null
  /** Always false: a calendar feed carries due dates, never proof of work. */
  evidence: boolean
  evidence_note?: string
}

export interface CanvasAssignment {
  uid: string
  title: string
  course: string | null
  due_at: string
  all_day: boolean
  url: string | null
  description: string | null
  imported_quest_id?: string | null
}

export interface CanvasOverview {
  link: CanvasLink
  assignments: CanvasAssignment[]
  imports: { source_key: string; quest_id: string | null }[]
  meta?: import('./client').Meta
  error?: { code: string; message: string } | null
}
