# Compass 🧭

**Compass checks that you actually did the work.**

Set a goal and it becomes 3–7 concrete subgoals, each with an acceptance criterion and a plan for
what would count as proof. Finish a focus session and Compass re-reads your own Google Workspace
and GitHub accounts, extracts deterministic evidence — a file you edited, an email you sent, a
commit you pushed, a calendar block you kept — and closes the step only if that evidence is
actually there. Progress is earned, not asserted.

Everything runs on your own machine. There is no hosted server holding your goals, no connector
platform between you and your data, and no paid inference path: every model is re-verified as free
at the moment it is called, and when none qualifies Compass degrades to transparent local
fallbacks rather than reaching for a paid one. Access is read-only by construction — Compass can
read your accounts and can never write to them.

A pixel companion grows out of that verified progress. It is the product's face and the reason
logging work feels worth doing, but the verification underneath is what Compass actually is.

Connected data arrives through one free, self-hosted provider: **the Apps Script bridge**, a
read-only Web App you deploy in your own Google account
([`college-os/bridge/`](college-os/bridge/README.md)), plus a free GitHub PAT. No connector
platform, no Cloud Console and no bill — nothing but your own OAuth grant reads your account. The
script's manifest turns on the Google APIs it needs as advanced services, so deploying is: paste
two files, run one function, click Deploy.

The full product/architecture specification lives in [PLAN.md](PLAN.md).

Compass began as a hackathon project built with
[@justanotherinternetguy](https://github.com/justanotherinternetguy) and has since been rebuilt as
a working local-first application. This repository is the public release of that work; both
authors are credited under the MIT licence.

## Stack

- **Backend:** Python · FastAPI · Pydantic · httpx · aiosqlite · Uvicorn (one process: API + WebSocket + built SPA)
- **Frontend:** React · TypeScript · Vite · React Router · TanStack Query
- **Persistence:** a single local SQLite database (WAL) with numbered migrations
- **AI:** free-only OpenRouter gateway — models must end in `:free`, report zero pricing, and support structured outputs; otherwise Compass uses transparent local fallbacks. It never calls a paid model or `openrouter/auto`.

## Setup

```bash
cp .env.example .env   # then fill in your keys (see below)
make setup             # venv + backend deps + npm install
make migrate           # apply SQLite migrations
make dev               # FastAPI (:8000) + Vite (:5173) together
```

Open http://localhost:5173. For a single-process "release" build:

```bash
make build             # lint, typecheck, test, build the SPA
make serve             # FastAPI serves SPA + API + WebSocket on :8000
```

`make test` runs the backend suite (122 tests, all offline — the data provider and OpenRouter are
mocked at the transport layer) plus the frontend typecheck and lint. CI runs the same on every push.

### Environment (.env at the workspace root)

| Variable | Required | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | yes | Used **only** for verified-free models |
| `COMPASS_APP_SECRET` | yes | Any long random string. Derives the key that encrypts stored provider credentials — changing it means re-entering your tokens. |
| `COMPASS_BRIDGE_URL` / `COMPASS_BRIDGE_TOKEN` | for connected data | Your Apps Script bridge deployment. Can be set per profile in Settings → Connections instead. |
| `COMPASS_GITHUB_TOKEN` | no | Read-only GitHub PAT |
| `COMPASS_DRIVE_OWNED_ONLY` | no | Restrict Drive reads to files you own, excluding shared-in files. Off by default; requires a bridge deployed from the current `api.gs`. |
| `OPENROUTER_MODEL` / `OPENROUTER_FALLBACK_MODELS` | no | Preference order; every candidate is re-verified as free at runtime |
| `COMPASS_BIND_HOST`, `COMPASS_PUBLIC_MODE`, `COMPASS_FRONTEND_ORIGIN` | no | Default binding is `127.0.0.1`; public mode enforces origin checks |
| `COMPASS_DEMO_MODE` | no | Enables 1-minute demo focus sessions |

Setting up connected data: follow
[`college-os/bridge/README.md`](college-os/bridge/README.md), then paste the deployment URL and
token into Settings → Connections. Nothing else is needed.

## How it works

1. **Profiles** — each browser gets a local profile with its own provider credentials (an Apps
   Script bridge deployment plus an optional GitHub PAT), an HttpOnly session cookie (only hashes
   are stored), and a one-time recovery code.
2. **Interest scan** — after explicit consent, Compass samples ≤18 recent Docs/Sheets/Slides
   (≤4,000 chars each, ≤32,000 total) and asks a free model for editable interest/aesthetic
   suggestions. Excerpts stay in process memory; only fingerprints and short labels persist.
3. **Quests** — a goal becomes 3–7 editable subgoals, each with an acceptance criterion and an
   evidence plan chosen from internal enums (the LLM never sees MCP tool names).
4. **Focus sessions** — the server owns all timing. With one explicit browser screen-share,
   Compass samples private still frames during active work and builds a separate attention view
   (direct work, supporting work, detours, streaks, and recovery). Raw frames live only in a local
   temporary directory and are deleted after analysis; no audio, camera, keystrokes, or clipboard
   are captured. Starting uses cached telemetry only;
   finishing refreshes each required provider once, extracts deterministic evidence, and asks
   the free model whether the subgoal looks complete (≥0.50 → verified, ≤0.35 → not completed,
   otherwise you decide — with an honest evidence card either way).
5. **Rewards** — a deterministic focus score against *your own* recent baseline, with idempotent
   XP, care points and stats feeding the companion. Deliberately not a pressure system: the
   companion never dies, never guilt-trips, and absence never drops mood below 30. There are no
   streaks to break and no ranking against anyone else.
6. **Focus rooms** — a shared room exposes only presence and a timer. Goals, filenames, repos
   and evidence never enter a room payload. Head-to-head battles, party bosses and the league
   board were removed: competitive ranking is evidence-negative for this audience, and both
   needed a second live player Compass has no user base to supply.
7. **Deadlines** — paste your personal Canvas Calendar Feed URL (Canvas → Calendar → Calendar
   Feed) and Compass reads upcoming assignments and turns them into quests with their real due
   dates. No token and no admin approval: student access tokens are being restricted and OAuth
   needs an institutional developer key, so the feed is the only self-serve door. Courses graded
   through Gradescope, Pearson or LabFlow can hold deadlines Canvas never sees, so any number of
   additional iCalendar feeds can be added alongside. Feeds carry deadlines, not proof —
   verification still comes from Drive, Gmail, Calendar or GitHub.
8. **College OS** — if [`college-os/`](college-os/README.md) has provisioned your Google account,
   Compass detects the COLLEGE DASHBOARD and turns its rows into quests (see below).

## College OS

[`college-os/`](college-os/README.md) is an Apps Script provisioner that builds a Google Workspace
operating system in your own account: the `COLLEGE` Drive tree, the **COLLEGE DASHBOARD**
spreadsheet, five calendars, six Tasks lists, and a Gmail label tree. Compass already reads Google
Workspace read-only, so the **College** page turns that structure into product objects:

| College OS | becomes in Compass |
|---|---|
| `SEMESTER GOALS` rows | quests, with the *Metric* as the acceptance criterion |
| `THIS WEEK` area goals + Big 3 | quests targeted at the coming Sunday, with the *Definition of Done* |
| `OPPORTUNITIES` (incl. the weekly Duke scan) | a pipeline view; open rows are importable as quests |
| the sheet's own `Evidence` column | the evidence specs Compass looks for after a focus session |
| `WEEKLY REVIEWS` | outcome mix, GOAL/PLAN/EXECUTION failure diagnosis, and your evidence-citation rate |
| `TIME LOG` | per-category estimate multipliers, recomputed and only shown once there are ≥3 samples |

Open **College** in the sidebar and hit *Detect* — it looks for a spreadsheet named
`COLLEGE DASHBOARD` in the connected Drive. Imports are idempotent: a row that already became a
quest is never imported twice, and the quest keeps a `college_os` marker pointing back at its row.
An `Evidence` cell Compass cannot observe honestly degrades to manual confirmation instead of
pretending — today that means `Tasks` rows, since Compass does not yet consume Google Tasks. (The
Apps Script bridge already serves them; it needs a `task_completed` evidence type to land.)

This integration inherits every guarantee in [Privacy](#privacy): it is read-only by construction, so
Compass can never edit the sheet, the calendars, Tasks, Drive, or Gmail. Only the *link* (file ids)
and the *import ledger* (which row became which quest) reach SQLite; dashboard cell contents are
fetched uncached and held in process memory for the page render only.

## Privacy

- All persistence is one local SQLite file (`backend/compass.db`). Delete it and everything is gone.
- Raw file content is never written to disk, logs, caches, or job records.
- Raw focus screenshots are temporary local files, never SQLite records or LLM-cache entries, and
  are deleted after analysis, cancellation, or server crash recovery.
- Sensitive-attribute inference is explicitly forbidden in every prompt, and connected content is
  delimited as untrusted data (prompt-injection resistant).
- Settings → Privacy offers full JSON export, memory deletion, cache deletion, and one-click
  profile deletion.
- Read-only by construction: a write-verb denylist plus a read allowlist means Compass cannot
  create, send, update, or delete anything in your connected accounts.

## Free-model limitations & troubleshooting

- **"Free AI temporarily unavailable"** — no catalog model passed verification, or your
  OpenRouter key was rejected (check `Settings → Connections → Free AI status`; a 401 in the
  server log means the key itself is invalid). Compass keeps working with local fallbacks:
  filename-based interest tags, manual quest plans, human-confirmed verification, template
  dialogue. It will never silently switch to a paid model.
- Free endpoints rate-limit aggressively; Compass queues requests (one in flight globally),
  batches companion dialogue, caches all deterministic LLM outputs, and retries 429s with
  backoff at most twice across at most two free models.
- **Connector shows `disconnected`** — check the bridge card in Settings → Connections
  (`bridge_not_public` means the Web App wasn't deployed with "Anyone" access). Statuses are
  cached for 5 minutes.
- **`google_meet` shows `unsupported`** — expected. The Meet API needs a Google Cloud project, so
  Compass reports it honestly instead of offering evidence it cannot observe.
- **Stale analytics badge** — the provider was unreachable, so cached data was served with a
  visible freshness label. Use the per-connector refresh (60s cooldown) when it's back.

## Seeing the whole loop

The shortest path to watching a claim get checked against real evidence:

1. `make serve`, then open `Settings → Connections` — healthy connectors and the active `:free`
   model.
2. Run onboarding. Connecting accounts is optional and the flow says so: skip it and you go
   straight to choosing a companion, with every step closing on your own confirmation. Connect
   the bridge first and you also get the bounded interest scan, whose inferences are editable
   before anything is saved.
3. Create a goal and review the subgoals and evidence plan the model proposed — both are editable
   before you activate. (Or open **College** → *Detect* and import a `SEMESTER GOALS` row, where
   the sheet's own Definition of Done and Evidence column drive the acceptance criterion.)
4. **The part that matters:** start a 1-minute session from Home, make a real change in a
   connected app — create a Google Doc, push a commit — then finish. Compass refreshes only the
   providers that step needs, extracts the evidence, shows you exactly what it found, and closes
   the subgoal only if the evidence supports it.
5. Repeat step 4 *without* doing the work. The step does not close, and the evidence card says
   why rather than pretending.
6. Open **Deadlines**, paste a Canvas Calendar Feed URL, and import an assignment — it becomes a
   quest with its real due date.
7. Open two browsers → two independent profiles. Join a focus room with the six-character code
   from the second one: both timers run, and neither side can see the other's goal, file or
   evidence.
8. `Insights → System` — cache savings, provider freshness, and the verification history.
9. Remove the OpenRouter key or drop the network and repeat a finish. Compass falls back to local
   plans and human confirmation and says "Free AI temporarily unavailable". No paid request is
   ever made.
