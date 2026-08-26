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

## Operating Context

- Work lives in Google Workspace and GitHub; Compass reads, never authors, that work.
- **College OS** is central, not a module: an Apps Script provisioner builds a `COLLEGE
  DASHBOARD` spreadsheet (`SEMESTER GOALS`, `THIS WEEK`, `OPPORTUNITIES`, `WEEKLY REVIEWS`,
  `TIME LOG`), a `COLLEGE` Drive folder, academic calendars and Gmail filters. Dashboard rows
  import directly into quests, and the sheet's `Evidence` column determines what Compass
  watches for.
- Connected data arrives through a read-only Apps Script Web App the student deploys in their
  own Google account, plus a read-only GitHub PAT.
- Focus sessions are the unit of work, with optional screen monitoring whose frames are
  analysed and deleted rather than retained.
- Multiplayer: synchronised focus battles and party boss encounters.
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
4. **Privacy survives multiplayer.** Social features expose readiness, placement and a generic
   category — never goals, filenames, or evidence.
5. **Say what isn't possible.** Unsupported connectors, unavailable AI and unverifiable
   evidence are reported honestly instead of quietly faked.
