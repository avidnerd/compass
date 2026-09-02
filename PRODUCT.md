# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

College students inside a semester. They are managing coursework, research or lab
applications, personal projects and opportunities at once, with the actual work spread across
Google Workspace (Drive, Docs, Sheets, Slides, Calendar, Gmail) and GitHub. The job: turn a
vague semester intention into concrete work, focus on it, and get credit for progress that
genuinely happened rather than progress they claimed.

A second, non-user audience is confirmed: engineers evaluating the repository itself. See
Product Purpose — both audiences are real and neither is decorative.

## Product Purpose

Compass reads a student's own work telemetry, turns a goal into editable subgoals, verifies
progress from deterministic evidence, and feeds a pixel companion that grows as they do.
Focus sessions can be run head-to-head with friends without either side revealing what they
are working on.

Success has two confirmed halves. The repository must demonstrate engineering judgement to
people assessing the author's work, **and** people the author does not know must be able to
install and run it. Neither half alone is the goal, which means setup friction and error
recovery are product problems, not polish.

## Positioning

Progress is verified from the student's own connected accounts, interpreted only by models
proven free at the moment of the call, on hardware the student owns. A neighbouring product
could copy the companion or the quests, but not the combination of: no connector platform
between the user and their data, no paid inference path even as a fallback, and no hosted
server holding anyone's goals.

Compass deliberately does not compete students against each other. Ranking is the obvious
move for this category and the evidence is against it, so the social surface is co-presence
only.

## Operating Context

- Work lives in Google Workspace and GitHub; Compass reads, never authors, that work.
- **College OS** is central, not a module: an Apps Script provisioner builds a `COLLEGE
  DASHBOARD` spreadsheet (`SEMESTER GOALS`, `THIS WEEK`, `OPPORTUNITIES`, `WEEKLY REVIEWS`,
  `TIME LOG`), a `COLLEGE` Drive folder, academic calendars and Gmail filters. Dashboard rows
  import directly into quests, and the sheet's `Evidence` column determines what Compass
  watches for.
- Connected data arrives through a read-only Apps Script Web App the student deploys in their
  own Google account, plus a read-only GitHub PAT.
- **Canvas** is read through the student's personal calendar-feed URL (Canvas → Calendar →
  Calendar Feed). The other two doors are closed to this product and should not be
  re-investigated: personal access tokens are capped at 120 days for student roles and can be
  disabled per institution (some already have), and OAuth2 needs a developer key an institution
  admin issues — Instructure's docs state plainly that an app cannot be used without the
  institution's permission, which is the connector platform Compass refuses to be. The feed
  carries due dates only: no submission status and no grades, so a Canvas assignment can seed a
  quest but can never verify one.
- Canvas is not the whole timetable. Courses graded through **Gradescope, Pearson MyLab/Mastering
  or LabFlow** keep their own deadlines: Gradescope on LTI 1.3 usually syncs its due date into
  Canvas, LTI 1.0 only if the instructor typed it there, and Pearson only after the first grade
  sync — while extensions, late deadlines and section-specific dates are documented as never
  syncing. So Compass reads **any number of iCalendar feeds**, not just Canvas, and says on
  screen that a quiet list can mean a deadline lives somewhere it cannot see.
- Scraping those tools is refused, not deferred. None offers a student-usable API; every
  third-party bridge is a browser extension driving the student's live session, which would
  mean Compass holding a Gradescope or Pearson credential. That breaks the read-only,
  no-credential-custody posture the product is built on.
- Focus sessions are the unit of work, with optional screen monitoring whose frames are
  analysed and deleted rather than retained.
- Focus rooms: working alongside other people, sharing only presence and a timer. Head-to-head
  battles, party boss encounters and the league board were removed in August 2026 — competitive
  ranking is evidence-negative for this audience (leaderboards demotivate everyone but the top
  and reduce peer social engagement regardless of how competitive a student is), and both needed
  a live second player Compass has no user base to supply. Co-presence, the mechanism with real
  support behind it, is what survives.
- Students often already hold a brief, assignment sheet or task list; those can seed a quest
  directly instead of a model inventing a breakdown.

## Capabilities and Constraints

- Evidence types Compass can observe: file created/modified, document, sheet and presentation
  content changed, email sent, calendar event completed, GitHub commit, PR opened, PR merged,
  checks passed, and manual confirmation.
- A quest holds 3–7 subgoals. A document listing more tasks is consolidated, never truncated
  silently.
- Google Meet is unsupported and reported as such: its API requires a Google Cloud project,
  which is the cost this design avoids.
- Google Tasks is served by the bridge but consumed by nothing — there is no `task_completed`
  evidence type yet.
- Deploying the bridge requires enabling four Google APIs as Apps Script **advanced services**.
  Apps Script's default Cloud projects are hidden and cannot be opened in the Cloud Console, so
  the Console route does not work at all.
- Compass installs as a Python package with a `compass` command that starts the local
  server and opens the user's own browser. It is deliberately not a desktop-webview app:
  the focus monitor depends on `getDisplayMedia`, which Tauri's webview cannot raise on
  macOS and which Electron replaces with an incompatible `desktopCapturer` API. Wrapping
  it would break or require rewriting that feature.
- The OpenRouter key is bring-your-own, entered in the UI and encrypted per profile; the
  environment variable remains a fallback for source checkouts and CI. The app secret is
  generated on first run and the database lives in the platform's per-user data directory,
  so an installed copy needs no `.env` at all.
- Three install paths exist: `uv tool install` straight from the git URL (a build hook
  compiles the interface), a wheel, and a standalone PyInstaller binary for people without
  Python. Tagging `v*` builds all of them for macOS Intel and Apple Silicon, Linux and
  Windows, and smoke-tests each binary by starting it.
- **The binaries are unsigned and will stay unsigned** until someone buys an Apple
  Developer membership and a Windows code-signing certificate. macOS Gatekeeper and
  Windows SmartScreen warn once; the README documents the bypass, and the wheel is offered
  as the path that involves no downloaded executable. macOS builds are ad-hoc signed
  (`codesign --sign -`), which is free and unrelated — it does not clear Gatekeeper, but an
  unsigned arm64 binary can otherwise fail to launch at all.
- One process, one SQLite connection, in-process workers and timers. This suits a local-first
  app and rules out horizontal scaling or rolling restarts.
- Provider credentials are encrypted at rest with `COMPASS_APP_SECRET`.
- **Undecided:** whether read-only access is a permanent product commitment. Today it is
  enforced structurally — the bridge manifest requests only `*.readonly` scopes, so Google's
  OAuth layer, not Compass's code, guarantees nothing can be modified. That was offered as a
  binding constraint and not confirmed, so future work should treat the current behaviour as
  fact and the permanence as an open decision.

## Brand Commitments

- Name: **Compass** 🧭.
- A pixel companion that grows with the user is the product's face, not an ornament.
- Originated as a hackathon project with [@justanotherinternetguy](https://github.com/justanotherinternetguy);
  MIT licensed with both authors credited. Attribution is binding.

## Evidence on Hand

- `README.md` — current architecture and setup. `PLAN.md` — the original specification, marked
  as historical where it diverges from the code.
- `college-os/` — the Apps Script provisioner and the read-only bridge (`bridge/api.gs`).
- 105 automated tests, all offline, plus CI on every push.
- The bridge has been deployed and verified end-to-end on the author's own Google account.

Absences future work must not fabricate: there are no users beyond the two authors, no
testimonials, no benchmarks, no adoption or uptime numbers, no pricing, and no deployment
story beyond running it locally.

## Product Principles

1. **Progress is earned, not asserted.** Completion comes from deterministic evidence in the
   student's own accounts, not from them ticking a box.
2. **Free is a constraint, not a tier.** Every model is re-verified as free at call time; when
   none qualifies, Compass degrades to transparent local fallbacks rather than reaching for a
   paid one.
3. **The user's machine is the boundary.** Local-first, no hosted server holding anyone's
   goals, files or evidence.
4. **Privacy survives multiplayer.** Social features expose readiness, presence and a generic
   category — never goals, filenames, or evidence.
5. **Say what isn't possible.** Unsupported connectors, unavailable AI and unverifiable
   evidence are reported honestly instead of quietly faked.
