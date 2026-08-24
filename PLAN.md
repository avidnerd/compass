# Compass Implementation Plan

> **Status: original specification, kept for the record.**
>
> This is the plan Compass was built from. Two things have changed since:
> the paid Merge connector platform was replaced by a self-hosted read-only
> Apps Script bridge plus a GitHub PAT (so the capability registry no longer
> discovers tools over the network), and provider credentials are now
> encrypted at rest. Where this document and the code disagree, the code and
> the [README](README.md) are current.


## 1. Product Summary

### Audience and outcome

This document is for the engineer implementing Compass from scratch. After reading it, they should be able to build and demonstrate the complete local-first product without making additional product or architecture decisions.

Use the code in the "example" folder to see how to use Merge but don't actually use the dashboard stuff.

Compass turns productivity telemetry into a personal, expressive game:

1. The user creates a local Compass profile.
2. Compass creates a distinct Merge Registered User for that profile.
3. The user connects Google Docs, Drive, Calendar, Sheets, Gmail, Slides, GitHub, and Google Meet through Merge's `fullpack`.
4. Compass performs a bounded scan of recent Google Workspace files.
5. A free OpenRouter model derives editable interests, aesthetics, and personality suggestions.
6. The user selects and names a layered pixel-art companion.
7. The user enters a goal; the LLM decomposes it into measurable subgoals.
8. The user completes a timed focus session.
9. Compass refreshes only relevant Merge data, extracts evidence, and asks the LLM whether the subgoal appears complete.
10. Verified effort grants XP, care points, companion stats, expressive reactions, and memories.
11. Users compete in synchronized focus battles or contribute verified sessions to party bosses.

The existing analytics dashboard remains available as an Insights section rather than being the main experience.

### Humane product rules

- Compare users to their own recent baseline, not raw output across different professions.
- Do not reward unnecessary commits, messages, meetings, or after-hours work merely for volume.
- The companion never dies, becomes sick, or shames the user for inactivity.
- When telemetry is inconclusive, disclose the uncertainty and ask the user.
- Explain every verification using a human-readable evidence card.
- Never expose private goals, filenames, repository names, messages, or evidence in multiplayer.
- Treat connected content as untrusted data, never as LLM instructions.
- Keep persistence, game simulation, rooms, jobs, and caches local.
- Use only OpenRouter models that are verifiably free. Never fall back to a paid model, `openrouter/auto`, or an unverified route.

### Expressive additions for “Make It Feel Human”

- A companion memory journal containing short, editable reflections—not raw work content.
- Daily companion “postcards” summarizing progress in the chosen voice.
- Distinct reactions for success, uncertainty, returning after a break, helping a party, and losing a friendly battle.
- User-editable personality and tone controls.
- Gentle recovery responses after an incomplete goal, including a suggested smaller next action.
- Party emotes and companion-to-companion reactions without unrestricted chat or moderation overhead.

## 2. Local Web Architecture

### Project organization

Normalize the prototype so the workspace root contains the backend, frontend, environment files, root task commands, README, and this plan.

Move the existing application out of the `merge dashboard example` wrapper. The current root `.env` is not found by the nested backend configuration, so environment loading must resolve from the workspace root.

Preserve the existing analytics functions and passing tests while migrating their routes and cache to the new user-scoped architecture.

### Runtime stack

- Backend: Python, FastAPI, Pydantic, `httpx.AsyncClient`, `aiosqlite`, and Uvicorn.
- Frontend: React, TypeScript, Vite, React Router, and TanStack Query.
- Persistence: one local SQLite database using WAL mode and explicit numbered migrations.
- Real-time updates: FastAPI WebSockets.
- Background jobs: persisted jobs consumed by an in-process `asyncio.Queue`.
- Companion artwork: local layered SVG assets animated with CSS.
- Development: Vite proxies `/api` and WebSocket traffic to FastAPI.
- Local release build: FastAPI serves the compiled SPA, API, and WebSocket endpoint from one process.
- Default network binding: `127.0.0.1`.
- LAN or tunnel access: explicit public mode with a configured application secret and allowed origin.

Do not introduce Redis, Celery, a cloud database, separate Google OAuth, image-generation services, or production matchmaking.

### Root commands

Provide:

- `make setup`: create the Python environment, install backend packages, and run `npm ci`.
- `make migrate`: apply SQLite migrations.
- `make dev`: start FastAPI and Vite together with clean shutdown handling.
- `make test`: run backend, frontend, and browser tests.
- `make build`: type-check, lint, test, and build the SPA.
- `make serve`: serve the built local app through FastAPI.

### Environment configuration

Required server-only values:

- `MERGE_API_KEY`
- `MERGE_TOOL_PACK_ID`
- `OPENROUTER_API_KEY`
- `COMPASS_APP_SECRET`

Free-model configuration:

- `OPENROUTER_MODEL=google/gemma-4-26b-a4b-it:free`
- `OPENROUTER_FALLBACK_MODELS=openai/gpt-oss-20b:free,nvidia/nemotron-3-super-120b-a12b:free,nvidia/nemotron-nano-9b-v2:free`

Optional configuration:

- `MERGE_REGISTERED_USER_ID`: imported once for the first legacy local profile.
- `COMPASS_FRONTEND_ORIGIN=http://localhost:5173`
- `COMPASS_TIMEZONE=UTC`
- `COMPASS_BIND_HOST=127.0.0.1`
- `COMPASS_PUBLIC_MODE=false`
- `COMPASS_DEMO_MODE=false`
- Existing cache TTL and work-hour values.

The model list is a default preference order, not permanent trust. Runtime validation must confirm that a model still:

1. Ends in `:free`.
2. Reports zero prompt and completion pricing.
3. Supports `response_format` and `structured_outputs`.
4. Is present in the current OpenRouter model catalog.

If none qualify, LLM-dependent work falls back to transparent manual behavior. Compass must never silently select a paid model.

### Local identity

Each browser creates a separate Compass profile.

Profile creation:

1. Generate a local UUID.
2. Create a Merge Registered User using the UUID as `origin_user_id`.
3. Store the resulting Merge Registered User ID on that profile.
4. Issue a random 256-bit session token in an HttpOnly, SameSite=Lax cookie.
5. Store only its hash in SQLite.
6. Display a one-time recovery code and store only that code's hash.

The existing `MERGE_REGISTERED_USER_ID` may seed the first profile only when the database contains no profiles. It must never be used as a global fallback for additional users.

Mutating cookie-authenticated requests validate their `Origin`. This is local-account security suitable for localhost, LAN, or a protected tunnel—not a production identity platform.

### Background jobs

Use persisted jobs for:

- Interest scanning.
- Quest decomposition.
- Session verification.
- Targeted telemetry refreshes.
- Daily companion postcards.
- Boss-theme generation.

States:

- `queued`
- `running`
- `succeeded`
- `failed`
- `canceled`

Each job records progress, safe error code, retry count, result resource, and timestamps. On startup, interrupted `running` jobs return to `queued`.

Concurrency limits:

- Two Merge jobs globally.
- One OpenRouter request globally because free endpoints may have strict rate limits.
- Four total local background jobs.
- One active OpenRouter job per profile.

## 3. Persistence, Privacy, and Caching

### Core records

SQLite will contain these logical records:

- `profiles`: identity, display name, timezone, work hours, Merge ID, onboarding state, and privacy settings.
- `auth_sessions`: profile, token hash, expiry, and last-used time.
- `connector_states`: profile, connector, status, capabilities, last check, and safe error.
- `interest_profiles`: editable topics, visual tags, tone, confidence, source fingerprint, and version.
- `source_summaries`: per-file derived labels and fingerprints; no raw body text.
- `characters`: sprite layers, personality, needs, XP, level, care points, stats, and version.
- `character_memories`: editable generated memories and visibility state.
- `quests`: goal, meaning, state, target date, and version.
- `subgoals`: order, acceptance criterion, evidence specifications, difficulty, and state.
- `focus_sessions`: authoritative timing, pauses, quest association, snapshots, score, and state.
- `telemetry_snapshots`: normalized metrics and source generations before and after sessions.
- `evidence_items`: source, event type, timestamp, hashed external reference, content hash, safe summary, and metric delta.
- `verifications`: result, confidence, evidence references, model, explanation, and human confirmation.
- `stat_ledger`: append-only rewards with a unique source-event key.
- `battles` and `battle_players`.
- `parties`, `party_members`, `boss_encounters`, and `boss_contributions`.
- `game_events`: replayable events for WebSocket recovery and the journal.
- `jobs`, `idempotency_records`, `tool_cache`, `analytics_cache`, and `llm_cache`.

Use foreign keys, UTC timestamps, ownership constraints, and a partial unique index permitting only one running or paused focus session per profile.

Discard the current unscoped cache during migration. It cannot safely be attributed to individual profiles.

### Merge capability registry

At startup and at most once every 24 hours:

1. Call Merge `tools/list`.
2. Discover the available read tools for Docs, Drive, Calendar, Sheets, Gmail, Slides, GitHub, and Meet.
3. Map them to internal logical capabilities.
4. Record missing tools as `unsupported` or `degraded`.
5. Reject all tools outside the read-only allowlist.

The LLM may select only internal evidence enums. It must never supply an MCP tool name or arbitrary tool arguments.

Compass must never invoke tools that create, send, update, delete, merge, upload, or alter permissions.

### Provider adapters

| Source | Bounded reads | Evidence |
|---|---|---|
| Drive | Recent/searchable file metadata | File creation, modification, MIME type |
| Docs | Selected document text | Content-hash changes |
| Sheets | Metadata and bounded cell values | Modified workbook and bounded-value hash |
| Slides | Presentation structure and bounded text | Modified deck and text hash |
| Calendar | Explicit time-window events | Planned focus blocks and meeting context |
| Gmail | Small sent-message searches | Relevant sent messages |
| GitHub | Selected repositories, commits, PRs, checks | Commits, PRs, merges, successful checks |
| Google Meet | Conference and participant records when permitted | Actual attendance and duration |

Calendar events are context, not proof of attendance. If Meet permissions are insufficient, mark attendance verification unavailable instead of pretending the scheduled event occurred.

### Automatic interest scan

Begin the scan automatically after Drive and at least one content connector are available, following a clear disclosure that bounded excerpts pass through Merge and a free OpenRouter model.

Limits:

- Search at most 60 recent native Workspace files from the previous 90 days.
- Sample no more than 18 files: up to 8 Docs, 5 Sheets, and 5 Slides.
- Cap each source at 4,000 normalized characters.
- Cap the total model input at 32,000 characters.
- Sheets: at most 200 non-empty cells across three visible tabs.
- Slides: titles and no more than 40 text elements.
- Skip trashed items, binaries, comments, hidden sheets, speaker notes, and inaccessible files.

Safety and privacy:

- Delimit excerpts as untrusted data.
- Explicitly tell the model to ignore instructions embedded in files.
- Do not infer sensitive attributes including health, religion, politics, sexuality, race, or finances.
- Keep excerpts in process memory only.
- Never place excerpts in logs, job records, general tool cache, or LLM cache.
- Store only fingerprints, modified times, short derived topic labels, and the final editable interest profile.
- Reuse a derived per-file summary until its modified-time fingerprint changes.

Output:

- Up to five interest themes.
- Palette and visual motif from allowed enums.
- Suggested accessories and habitat props.
- Three personality presets.
- Three optional names.
- Confidence and a short explanation.

The user must be able to edit all inferred fields before creating the companion.

### Cache rules

Every persistent provider cache key includes:

- Profile or Merge Registered User ID.
- Connector.
- Logical capability.
- Canonical arguments.
- Cache schema version.

| Data | Default cache |
|---|---:|
| Merge tool list | 24 hours globally |
| OpenRouter model catalog | 24 hours globally |
| Credential validation | 5 minutes per profile/connector |
| Drive metadata | 2 hours |
| Calendar events | 20 minutes |
| Gmail activity | 20 minutes |
| Meet records | 30 minutes |
| GitHub activity | 30 minutes |
| Analytics | 15 minutes |
| Per-file derived interest summary | Until file fingerprint changes |
| Quest plan | Immutable by model/prompt/input hash |
| Verification | Immutable by model/snapshot/prompt hash |
| Companion dialogue batch | 24 hours by event/persona hash |

Behavior:

- Bucket time windows to stable boundaries.
- Use a per-key in-process single-flight lock.
- Serve stale analytics with a visible freshness label when Merge is down.
- Never use stale evidence for automatic quest completion.
- Starting a focus session uses cached telemetry and makes no forced provider call.
- Finishing refreshes each required provider once.
- Rechecking uncertain evidence has a two-minute cooldown.
- Never poll Merge or OpenRouter automatically from the frontend.
- Connector refresh increments that profile's connector generation.
- Analytics cache keys contain dependency generations, avoiding broad invalidation.
- Manual refresh has a 60-second profile/connector cooldown.
- Cache statistics expose hits, misses, stale serves, refresh time, and avoided calls without exposing payloads.

### Free-only OpenRouter gateway

All LLM calls pass through one server-side gateway.

`resolve_free_model()` must:

1. Fetch or read the cached OpenRouter model catalog.
2. Evaluate the configured primary and fallback IDs in order.
3. Require `:free`, zero prompt price, zero completion price, and structured-output support.
4. Reject `openrouter/auto`, paid variants, aliases without a `:free` suffix, and unknown pricing.
5. Return no model if none qualify.

Request policy:

- Planning, profiling, and verification temperature: `0.2`.
- Dialogue and postcards temperature: `0.8`.
- Timeout: 30 seconds, accounting for free-tier latency.
- Retry transient 429/5xx responses at most twice with `Retry-After` and jitter.
- Try at most two different free models for one job.
- Never retry into a paid route.
- Validate structured output with Pydantic.
- Retry malformed structured output once with a compact validation error.
- Store the actual model ID on every generated artifact.

Free-tier conservation:

- Cache all safe deterministic outputs.
- Batch three companion dialogue lines into one request.
- Generate no more than one daily postcard per profile.
- Do not call the LLM for animations, timers, care actions, or deterministic scoring.
- Reuse quest plans until the goal or planning inputs change.
- Reuse verification until its telemetry snapshot changes.
- Queue requests rather than racing free-model rate limits.

Fallback behavior when no free model is available:

- Interest scan produces deterministic filename-based tags for user review.
- Quest creation produces one editable manual-verification subgoal.
- Verification becomes `needs_confirmation`.
- Companion dialogue uses local templates.
- Bosses use local predefined themes.
- The UI shows “Free AI temporarily unavailable”; it never suggests adding payment.

## 4. Product Features

### Onboarding

1. **Profile:** display name, timezone, work hours, recovery code.
2. **Connections:** cards for all eight supported connectors and Merge Magic Links.
3. **Disclosure:** explain exactly what is scanned and what is sent to OpenRouter.
4. **Interest scan:** show progress, source counts, free-model status, and safe errors.
5. **Interest review:** edit or remove inferred topics and aesthetic choices.
6. **Companion selection:** present three layered eggs.
7. **Customization:** name, pronouns, tone, palette, markings, accessory, habitat.
8. **First quest:** enter a custom goal or select a small suggested goal.

Onboarding state persists across refreshes and server restarts.

### Companion

Local SVG layers:

- Body/species.
- Palette.
- Eyes and expression.
- Markings.
- Accessory.
- Aura.
- Habitat and props.

The LLM selects enums only. It cannot produce HTML, CSS, SVG, scripts, or URLs.

Persistent attributes:

- XP and level.
- Care points.
- Energy, mood, and bond.
- Focus, Curiosity, Craft, Communication, Collaboration, and Balance.
- Current expression and animation.
- Personality voice.
- Memories.

Care actions:

- `feed`: costs 1 care point; adds 15 energy.
- `play`: costs 1 care point; adds 12 mood and one daily bond point.
- `rest`: free; restores energy gradually.
- `decorate`: purchases unlocked local cosmetics.
- `encourage`: stores a short user-authored private memory.

Absence never lowers mood below 30. Needs drift toward neutral instead of creating punishment. The companion cannot die.

Evolution occurs at levels 3, 7, and 12. Each evolution offers two cosmetic forms based on dominant stats and interests. Previous layers remain available.

### Quest planning

Quest input:

- Goal.
- Optional reason or personal meaning.
- Target date.
- Preferred session length.
- Optional target files, repositories, or connector categories.
- Whether a generic activity category may appear in multiplayer.

The free model proposes three to seven subgoals containing:

- Title and rationale.
- Acceptance criterion.
- Estimated number of sessions.
- Difficulty from 1–5.
- Required connector capabilities.
- Evidence specifications.
- Manual fallback.

Allowed evidence types:

- `file_created`
- `file_modified`
- `document_content_changed`
- `sheet_values_changed`
- `presentation_content_changed`
- `email_sent`
- `calendar_event_completed`
- `github_commit_created`
- `github_pull_request_opened`
- `github_pull_request_merged`
- `github_checks_passed`
- `meet_attended`
- `manual_confirmation`

Users review, edit, reorder, add, or delete subgoals before activating the quest.

Quest states:

- `draft`
- `planning`
- `active`
- `completed`
- `archived`

Subgoal states:

- `todo`
- `in_progress`
- `verifying`
- `needs_confirmation`
- `completed`

### Focus sessions

Session states:

- `running`
- `paused`
- `ending`
- `completed`
- `canceled`

The server owns timestamps and pause intervals. Browser timers render from authoritative server time.

Start:

1. Verify there is no other active session.
2. Capture the latest cached baseline.
3. Record evidence targets and connector generations.
4. Start the timer.
5. Broadcast a focus event.

Finish:

1. Freeze timing idempotently.
2. Refresh only required evidence providers.
3. Capture final normalized telemetry.
4. Extract deterministic evidence.
5. Ask a validated free model to interpret the evidence.
6. Store verification and explanation.
7. Apply idempotent rewards.
8. Broadcast quest, character, battle, and party changes.

### Verification

Outcomes:

- Confidence `>= 0.80` with sufficient evidence: `verified`.
- Confidence `<= 0.35` or clear contradiction: `not_completed`.
- Otherwise: `needs_confirmation`.

The UI shows:

- What Compass observed.
- What it could not observe.
- Which connected source supplied the evidence.
- The free model's short interpretation.
- “Yes, I completed it,” “Not yet,” and “Recheck evidence.”

Human-confirmed completion receives 80% of normal XP and stat rewards. Rejecting returns the subgoal to `in_progress`.

If no free model is available, deterministic evidence is displayed but the result remains `needs_confirmation`.

### Focus score and progression

For a completed session:

- `commitment = min(active_seconds / planned_seconds, 1)`
- `completion = 1.0` for verified, `0.75` for user-confirmed, and `0` otherwise.
- `continuity = max(0, 1 - paused_seconds / total_session_seconds)`
- `improvement` is the current session's percentile against the user's prior 14 eligible sessions; use `0.5` until five prior sessions exist.
- `focus_score = round(100 × (0.30×commitment + 0.45×completion + 0.15×continuity + 0.10×improvement))`

Rewards:

- `xp = 10 + floor(focus_score / 5)`
- `care_points = 1 + floor(focus_score / 25)`
- Focus stat: +1 at score 60–84 and +2 at 85+.
- The primary evidence stat receives the same increase.
- Human-confirmed sessions cap stat growth at +1.
- Eligible co-op contributions grant +1 Collaboration at most once per day.
- Stats cap at 100.
- Cumulative level threshold: `25 × level × (level + 1)`.

Evidence mapping:

| Evidence | Stat |
|---|---|
| Docs, Sheets, Slides | Curiosity or Craft |
| GitHub implementation/checks | Craft |
| Gmail communication | Communication |
| Google Meet collaboration | Communication or Collaboration |
| Calendar focus block and healthy timing | Focus or Balance |
| Party contribution | Collaboration |

### Companion reactions and memories

The free-model reaction function receives only:

- Companion persona.
- Safe or generic quest label.
- Verification outcome.
- Reward changes.
- Recent high-level memories.
- Multiplayer result.

It returns three short lines in one request:

- Immediate reaction.
- Optional encouragement.
- Journal memory.

The companion must explicitly admit uncertainty. Raw filenames, excerpts, emails, and repository names are never used in dialogue unless the user explicitly chose to expose that title locally.

### Focus battles

A battle is a synchronized sprint for 2–4 users.

States:

- `waiting`
- `countdown`
- `active`
- `resolving`
- `completed`
- `canceled`

Flow:

1. Host selects 15, 25, or 50 minutes; demo mode includes one minute.
2. Other users join with a six-character code.
3. Each player privately selects a subgoal.
4. Players mark ready.
5. Host starts a five-second countdown.
6. The server creates linked focus sessions.
7. During play, clients see only timer, connectivity, companion animation, and generic momentum.
8. Each player is verified independently.
9. The server resolves and broadcasts the podium.

Battle power:

- `75%` from personal-baseline focus score.
- `15` points for verified completion or `8` for human-confirmed completion.
- Up to `10` points from the relevant stat.
- Cap at 100.
- Scores within two points are a draw.
- Leaving forfeits placement but does not remove legitimate personal focus rewards.

No private goal or evidence data enters the room payload.

### Parties and co-op bosses

Parties support up to six members and contain:

- Name.
- Invite code.
- Shared visual theme.
- Preset emotes.
- Active boss.
- Contribution history.

Boss encounters last 24 hours by default.

Difficulty multipliers:

- Easy: `1.0`
- Standard: `1.5`
- Epic: `2.0`

Rules:

- `boss_hp = round(100 × member_count_at_start × difficulty_multiplier)`
- Each eligible focus session contributes once.
- `damage = round(20 + 0.60×focus_score + 2×min(character_level, 10))`
- Human-confirmed damage is multiplied by `0.8`.
- Battle sessions may also contribute to a party boss.
- Zero HP defeats the boss.
- Expiry has no punishment.

Defeating a boss grants a local cosmetic, habitat prop, and companion memory.

A free model may create the boss name and narration from non-sensitive overlapping interest tags. Boss HP, damage, eligibility, and rewards remain deterministic. If free AI is unavailable, select from bundled boss themes.

### Insights and settings

Retain the existing analytics as:

- Overview.
- Calendar.
- Documents.
- Email.
- Google Meet.
- GitHub.
- Collaboration.
- Trends.

Add:

- Personal baseline.
- Session history.
- Stat growth.
- Provider freshness.
- Cache savings.
- Verification history.

Settings:

- Connections.
- Profile and work hours.
- Companion voice and animation.
- Privacy and multiplayer sharing.
- Free-model status and selected model.
- Interest rescan.
- Memory deletion.
- Connector-cache deletion.
- Local JSON export.
- Complete profile deletion.

## 5. Backend Function Contracts

### Bootstrap

- `load_settings() -> Settings`: load the root environment and validate secrets.
- `run_migrations()`: apply numbered SQLite migrations transactionally.
- `seed_legacy_profile()`: import the legacy Merge ID once.
- `discover_capabilities(force=False) -> CapabilityRegistry`
- `refresh_free_model_catalog(force=False) -> ModelCatalog`
- `resolve_free_model(preferences) -> FreeModel | None`
- `resume_jobs()`: requeue interrupted jobs and start workers.

### Merge and cache

- `create_merge_identity(profile_id) -> str`
- `create_link_token(profile_id, connector) -> str`
- `validate_connections(profile_id, force=False) -> list[ConnectorState]`
- `call_tool(profile_id, logical_capability, arguments, cache_policy) -> ToolResult`
- `canonical_cache_key(profile_id, capability, arguments, schema_version) -> str`
- `get_or_fetch(...) -> CachedResult`
- `get_or_compute(...) -> CachedResult`
- `invalidate_connector(profile_id, connector) -> int`
- `cache_stats(profile_id) -> CacheStats`

`call_tool` must resolve an allowlisted logical capability, apply bounds, use the profile's Merge identity, redact errors, and reject write tools.

### Telemetry

- `search_recent_workspace_files(profile_id, limit, modified_after)`
- `summarize_document(profile_id, file_ref)`
- `summarize_sheet(profile_id, file_ref)`
- `summarize_presentation(profile_id, file_ref)`
- `calendar_activity(profile_id, start, end)`
- `sent_email_evidence(profile_id, start, end, search_terms)`
- `github_activity(profile_id, start, end, repositories)`
- `meet_activity(profile_id, start, end)`
- `capture_snapshot(profile_id, evidence_specs, phase) -> TelemetrySnapshot`
- `extract_evidence(baseline, final, evidence_specs) -> list[EvidenceItem]`

All time windows, pagination, repository counts, file counts, and content sizes are hard-capped.

### Free-model LLM gateway

- `call_free_structured(prompt, schema, purpose) -> ValidatedResult`
- `infer_interest_profile(samples) -> InterestProfileDraft`
- `decompose_quest(goal, capabilities, interests) -> QuestPlan`
- `evaluate_subgoal(subgoal, evidence) -> VerificationDraft`
- `generate_reaction(persona, event) -> ReactionBatch`
- `generate_boss_theme(safe_tags) -> BossTheme`
- `generate_daily_postcard(persona, safe_events) -> Postcard`

`call_free_structured` owns model validation, rate-limit handling, fallback order, schema validation, output caching, and the invariant that no paid route can be called.

### Domain services

- `create_profile(input) -> Profile`
- `start_interest_scan(profile_id) -> Job`
- `finalize_companion(profile_id, selection) -> Character`
- `create_quest(profile_id, input) -> Quest`
- `apply_quest_plan(quest_id, plan) -> Quest`
- `activate_quest(profile_id, quest_id) -> Quest`
- `start_focus_session(profile_id, input, idempotency_key) -> FocusSession`
- `pause_focus_session(...)`
- `resume_focus_session(...)`
- `cancel_focus_session(...)`
- `finish_focus_session(...) -> Job`
- `resolve_verification(session_id, result)`
- `confirm_verification(profile_id, verification_id, accepted)`
- `calculate_focus_score(session, verification, baseline) -> int`
- `apply_rewards(event_id, reward)`
- `advance_character(profile_id)`
- `record_memory(profile_id, event)`

### Multiplayer

- `create_battle(host_id, options) -> Battle`
- `join_battle(profile_id, code) -> Battle`
- `set_battle_ready(profile_id, battle_id, ready)`
- `start_battle(host_id, battle_id)`
- `resolve_battle(battle_id)`
- `create_party(owner_id, input) -> Party`
- `join_party(profile_id, code) -> Party`
- `start_boss_encounter(profile_id, party_id, difficulty) -> BossEncounter`
- `apply_boss_contribution(session_id)`
- `resolve_boss(encounter_id)`
- `publish_event(audience, type, aggregate_id, payload) -> GameEvent`
- `replay_events(profile_id, after_event_id) -> list[GameEvent]`

REST performs mutations; WebSockets deliver authenticated server events only.

## 6. API and Frontend Routing

### API conventions

- Base path: `/api/v1`.
- Additive v1 evolution; breaking changes require `/api/v2`.
- Success envelope: `data` plus request/cache metadata.
- Error envelope: stable code, human message, details, and request ID.
- Cursor pagination with default 50 and maximum 100.
- `Idempotency-Key` for retriable actions.
- ETags and `If-Match` for mutable resources.
- Honest HTTP status codes; never a 200 error response.

### Identity and onboarding endpoints

- `POST /profiles`
- `POST /auth/recover`
- `DELETE /auth/session`
- `GET /me`
- `PATCH /me`
- `DELETE /me`
- `GET /onboarding`
- `GET /connections`
- `POST /connections/{connector}/link-token`
- `POST /connections/{connector}:refresh`
- `POST /interest-scans`
- `GET /interest-profile`
- `PATCH /interest-profile`
- `POST /interest-profile:rescan`
- `GET /jobs/{job_id}`
- `GET /system/free-models`

`GET /system/free-models` returns only model IDs, availability, last catalog check, and selected model. It exposes no OpenRouter key or pricing metadata beyond verified-free status.

### Character endpoints

- `GET /character`
- `POST /character`
- `PATCH /character`
- `POST /character/actions`
- `GET /character/memories`
- `PATCH /character/memories/{memory_id}`
- `DELETE /character/memories/{memory_id}`
- `GET /character/unlocks`

### Quest and focus endpoints

- `GET /quests`
- `POST /quests`
- `GET /quests/{quest_id}`
- `PATCH /quests/{quest_id}`
- `POST /quests/{quest_id}:activate`
- `POST /quests/{quest_id}:archive`
- `GET /focus-sessions`
- `POST /focus-sessions`
- `GET /focus-sessions/{session_id}`
- `POST /focus-sessions/{session_id}:pause`
- `POST /focus-sessions/{session_id}:resume`
- `POST /focus-sessions/{session_id}:finish`
- `POST /focus-sessions/{session_id}:cancel`
- `POST /verifications/{verification_id}:confirm`
- `POST /verifications/{verification_id}:recheck`

### Analytics endpoints

- `GET /analytics/summary`
- `GET /analytics/baseline`
- `GET /analytics/timeline`
- `GET /analytics/calendar`
- `GET /analytics/documents`
- `GET /analytics/email`
- `GET /analytics/meet`
- `GET /analytics/github`
- `GET /analytics/collaboration`
- `GET /telemetry/freshness`
- `GET /cache/stats`
- `POST /cache/{connector}:invalidate`

### Battle endpoints

- `POST /battles`
- `POST /battles:join`
- `GET /battles/{battle_id}`
- `POST /battles/{battle_id}:ready`
- `POST /battles/{battle_id}:start`
- `POST /battles/{battle_id}:leave`
- `POST /battles/{battle_id}:cancel`
- `GET /battles/{battle_id}/results`

### Party endpoints

- `POST /parties`
- `POST /parties:join`
- `GET /parties`
- `GET /parties/{party_id}`
- `PATCH /parties/{party_id}`
- `POST /parties/{party_id}:leave`
- `POST /parties/{party_id}/emotes`
- `POST /parties/{party_id}/boss-encounters`
- `GET /parties/{party_id}/boss-encounters/{encounter_id}`
- `GET /parties/{party_id}/contributions`

### WebSocket

Endpoint:

`/api/v1/ws?after=<last_event_id>`

Behavior:

1. Authenticate from the HttpOnly cookie.
2. Replay authorized events after the provided cursor.
3. Subscribe to the user, current battle, and current parties.
4. Send heartbeat pings.
5. Remove dead connections without blocking other clients.

Events:

- `job.updated`
- `connection.updated`
- `character.updated`
- `reaction.created`
- `quest.updated`
- `focus.updated`
- `verification.updated`
- `battle.updated`
- `battle.countdown`
- `battle.completed`
- `party.updated`
- `party.emote`
- `boss.updated`
- `boss.defeated`
- `free_model.updated`

### Frontend routes

| Route | Screen |
|---|---|
| `/` | Redirect to onboarding or home |
| `/onboarding/profile` | Profile and recovery code |
| `/onboarding/connect` | Merge connections |
| `/onboarding/scan` | Scan and free-model progress |
| `/onboarding/companion` | Companion selection |
| `/home` | Habitat, companion, active quest, quick focus |
| `/quests` | Quest collection |
| `/quests/new` | Goal entry and decomposition |
| `/quests/:questId` | Subgoals, evidence, history |
| `/focus/:sessionId` | Authoritative focus timer |
| `/character/customize` | Sprite and personality editing |
| `/character/journal` | Memories, stats, evolution, postcards |
| `/battle` | Create or join |
| `/battle/:battleId` | Lobby, sprint, results |
| `/party` | Parties and invite entry |
| `/party/:partyId` | Members, boss, emotes, contributions |
| `/party/:partyId/boss/:encounterId` | Live boss scene |
| `/insights` | Personal baseline |
| `/insights/calendar` | Calendar analytics |
| `/insights/documents` | Workspace analytics |
| `/insights/email` | Gmail analytics |
| `/insights/meet` | Meet analytics |
| `/insights/github` | GitHub analytics |
| `/insights/collaboration` | Collaboration analytics |
| `/settings/connections` | Connections and cache |
| `/settings/privacy` | Scan, sharing, export, deletion |
| `/settings/gameplay` | Work hours, motion, sound, tone |
| `*` | In-app 404 |

Frontend requirements:

- Desktop side navigation and mobile bottom navigation.
- Game-first home screen rather than dashboard-first layout.
- One WebSocket hook for event replay and query invalidation.
- Stable mutation idempotency keys across retries.
- Timers derived from server timestamps.
- No sensitive data in local storage.
- Reduced-motion support, keyboard navigation, semantic structure, and visible focus.
- Distinct offline, stale-data, Merge-unavailable, free-model-unavailable, and verification-uncertain states.

## 7. Delivery and Verification

### Milestone 1 — Foundation

- Normalize project layout and root configuration.
- Add migrations, profiles, cookies, ownership, v1 envelopes, request IDs, and user-scoped caching.
- Convert Merge access to bounded asynchronous calls.
- Add Merge capability discovery.
- Add free OpenRouter catalog discovery and enforce the free-only gateway.
- Serve the built SPA through FastAPI.

Exit: two browsers have independent profiles, Merge identities, caches, and sessions; a deliberately configured paid model is rejected before any LLM request.

### Milestone 2 — Personalization

- Implement bounded Workspace scanning.
- Add free-model structured-output profiling.
- Add deterministic filename-based fallback.
- Build interest review, layered companion selection, care actions, memories, and evolution.
- Add privacy controls and content-free logging.

Exit: onboarding creates a persistent customized companion using either a verified free model or the disclosed local fallback.

### Milestone 3 — Quests and focus

- Implement quest planning and editing.
- Add focus-session state machine and authoritative timer.
- Implement evidence adapters, snapshots, verification, confirmation, scoring, rewards, and stat ledger.
- Add evidence explanations and free-model outage behavior.

Exit: a real connected-app action can complete a subgoal and upgrade the companion without any paid model call.

### Milestone 4 — Multiplayer

- Implement WebSocket replay.
- Add synchronized battles, reconnection, scoring, and results.
- Add parties, emotes, boss lifecycle, contributions, and rewards.
- Audit multiplayer payloads for private data.

Exit: two browsers can complete a battle and jointly damage a boss using independently verified sessions.

### Milestone 5 — Insights and hackathon polish

- Move current dashboards into Insights.
- Add baseline, stat growth, freshness, cache savings, and verification history.
- Complete responsive visuals, accessibility, sound toggle, and expressive states.
- Add visibly labeled one-minute demo sessions.
- Document setup, free-model limitations, troubleshooting, privacy, and the demo flow.
- Link `PLAN.md` from the README.

### Unit tests

- Cache isolation and canonicalization.
- Connector-generation invalidation.
- Interest scan limits and raw-content non-persistence.
- Prompt injection inside connected documents.
- Free-model catalog filtering.
- Rejection of paid, auto-routed, missing-price, or non-`:free` models.
- No-paid-fallback invariant under 404, 429, 5xx, timeout, and malformed output.
- LLM schema validation and deterministic fallbacks.
- Quest, session, battle, and boss state machines.
- Focus score and baseline behavior.
- Reward idempotency and level thresholds.
- Timezones and DST.

### Integration tests

- Profile cookies, recovery, origin checks, and ownership.
- Distinct Merge Registered Users.
- Correct errors, status codes, pagination, ETags, and idempotency.
- One active focus session per profile.
- Duplicate finish requests cannot duplicate rewards.
- Profile deletion removes owned data and caches.
- Interrupted jobs recover after restart.
- Mock OpenRouter asserts every requested model ends in `:free`.
- Mock OpenRouter asserts no request targets `openrouter/auto`.
- No live API calls in the default suite.

### WebSocket and browser tests

- Two clients receive the same battle countdown.
- Unauthorized users cannot subscribe to another room.
- Reconnection replays missed events once.
- Server restart reconstructs timers and rooms.
- Complete onboarding and edit inferred interests.
- Create and activate a planned quest.
- Pause, resume, refresh, and finish a focus session.
- Exercise verified, incomplete, and uncertain outcomes.
- Complete a two-browser battle.
- Defeat a party boss.
- Confirm no private evidence appears in multiplayer.
- Verify free-model outage UI and local fallbacks.
- Navigate with keyboard and reduced motion.

### Judge demo

1. Start Compass and show healthy Merge capabilities plus a verified-free OpenRouter model.
2. Open two browser profiles.
3. Connect the first profile and run the bounded interest scan.
4. Edit an inferred interest and choose a companion.
5. Enter a meaningful goal and review the free model's subgoals and evidence plan.
6. Start a one-minute demo focus session and perform a real connected-app change.
7. Finish and show targeted refresh, evidence, verification, XP, care points, stat growth, animation, and memory.
8. Have the second browser join a focus battle.
9. Complete the battle and show normalized results.
10. Join a party and defeat a boss through verified contributions.
11. Show cache savings, privacy controls, and the active `:free` model.
12. Temporarily disable the free-model route and demonstrate that Compass falls back safely without making a paid request.

### Assumptions

- Only Google Docs, Drive, Calendar, Sheets, Gmail, Slides, GitHub, and Google Meet are supported.
- Zoom is completely out of scope.
- The existing analytics prototype remains the base.
- Multiplayer uses one local FastAPI process.
- SQLite and in-memory WebSocket fan-out are sufficient.
- Each participant has a separate Compass profile and Merge Registered User.
- Only OpenRouter models verified as zero-cost and ending in `:free` may be called.
- The initial preferred free model is `google/gemma-4-26b-a4b-it:free`, but availability is validated at runtime.
- Free models may be unavailable or rate-limited; local/manual fallback is required product behavior.
- Automatic Workspace scanning is bounded and disclosed.
- Raw excerpts may transit Merge and OpenRouter but are never persisted by Compass.
- No provider writes, production identity service, global matchmaking, paid model fallback, image generation, or hidden activity monitoring are included.
