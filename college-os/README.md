# College OS: setup

Provisions the Calendar / Tasks / Drive / Gmail / Sheets system in **your** Google account.

| File | What it does |
|---|---|
| `setup.gs` | Creates calendars, rhythms, task lists, the Drive tree, the dashboard sheet, Gmail labels + filters. Idempotent. |
| `duke-scan.gs` | Weekly job that trawls Duke's event feed and drops matches into the OPPORTUNITIES tab. |
| `appsscript.json` | Manifest: scopes and the two advanced services. |
| `gmail-filters.xml` | Fallback if you'd rather import filters by hand than run the Gmail half of the script. |
| `bridge/` | A **separate**, read-only Web App: how Compass reads your Google account, for free and with no connector platform in between. See [`bridge/README.md`](bridge/README.md). |

---

## Run it

1. Go to **script.google.com** and choose **New project**.
2. Paste `setup.gs` into `Code.gs`. Add a second file (`+` Script) and paste `duke-scan.gs`.
3. Click **Project Settings** and check *"Show appsscript.json manifest file"*. Open the manifest that appears in the editor and replace it with `appsscript.json`. Set `timeZone` if you aren't on Eastern.
4. In the left sidebar, open **Services** (`+`) and add **Tasks API** and **Gmail API**. The identifiers must read exactly `Tasks` and `Gmail`.
5. Optional but recommended: run **`whatWouldBeCreated`** first. It's a dry run: it prints what's missing and creates nothing.
6. Run **`setUp`**. Approve the OAuth screen (it's your own script, so Google shows the "unverified app" warning: choose *Advanced*, then *Go to project*).
7. Read the execution log. It prints the Drive folder and dashboard URLs.
8. Edit `INTERESTS` in `duke-scan.gs`, run **`scanDukeEvents`** once to eyeball the output, then run **`installWeeklyScan`**.

## Connecting it to Compass

Compass (the app in the repo root) reads this structure once it exists. Open **College** in the
sidebar and press *Detect*: it searches the connected Drive for a spreadsheet named
`COLLEGE DASHBOARD`, plus the `COLLEGE` folder and any `PROJECT HOME:` docs.

First connect Compass to your Google account with [`bridge/`](bridge/README.md)

Once linked, dashboard rows can be imported as Compass quests:

- `SEMESTER GOALS` a quest per outcome; the *Metric* becomes the acceptance criterion.
- `THIS WEEK` area goals and the Big 3 quests targeted at the coming Sunday, carrying the
  *Definition of Done*.
- Open `OPPORTUNITIES` rows (including whatever `duke-scan.gs` wrote) a quest per row, using the
  *Next Action* as the criterion and the *Deadline* as the target date.

The **Evidence** column is the load-bearing part of that translation. `Gmail` maps to sent-email
evidence, `Drive` to file created/modified, `Calendar` to a completed block, `GitHub` to commits and
merged PRs. `Tasks` maps to manual confirmation. Google Tasks isn't one of Compass's eight
connectors, and it says so rather than pretending. So the Definition of Done you write on Sunday is
literally what Compass checks for on Thursday.

Compass also reads the tabs the import flow ignores: `WEEKLY REVIEWS` becomes an outcome mix, a
GOAL/PLAN/EXECUTION failure diagnosis, and your evidence-citation rate; `TIME LOG` becomes
per-category estimate multipliers (recomputed from Estimated/Actual, and greyed out until a category
has at least three samples).

Two things worth knowing:

- **Nothing flows back.** Compass is read-only by construction: a write-verb denylist means it
  cannot create, edit, or delete anything in your Google account. It will never tick a checkbox,
  update the Progress column, or add a row. The Sunday reset is still yours to do.
- **The sheet's contents are never stored.** Compass keeps the file id and a ledger of which row
  became which quest. Cell text is fetched uncached, held in memory for the page render, and dropped.

Renamed things? Point Compass at them with `COMPASS_COLLEGE_ROOT_FOLDER` and
`COMPASS_COLLEGE_DASHBOARD_NAME` in the workspace `.env`.

---

## What you still have to do by hand

The API can't reach these:

- **Reorder your Tasks lists.** Drag `Inbox` to the top. There's no API for list order, and Inbox being first is the whole reason capture stays under five seconds.
- **Set task start times and durations.** Open a task from *Google Calendar* (not the Tasks app): that editor is where start time, duration, and a separate deadline live. This is the piece that makes the deadline-vs-work-session split work.
- **Add your class schedule** to Academic. Duke's registrar export or manual entry.
- **Tune the Gmail queries.** They're in `GMAIL_RULES` and they're guesses (see below).
- **Subscribe to the newsletters** you actually want feeding the funnel: Pratt, undergraduate research, Career Center, innovation/entrepreneurship, your departments, Bass Connections.

---

## Three things in the original plan that don't work as written

**1. Duke has no filtered calendar subscription.** I checked. `calendar.duke.edu` offers per-event `.ics` downloads and RSS/JSON feeds, but there's no subscribable `.ics` for a filtered view: and the JSON endpoint ignores `gs=` / `cs=` / `category=` filter params entirely (all four return the identical 280-event payload). So "subscribe Opportunities to Duke events" isn't available.

`duke-scan.gs` closes the gap the other way: it pulls the whole feed, filters client-side against your keywords, and writes candidates to the **OPPORTUNITIES sheet**: never to your calendar. You still make every attend/pass call yourself on Sunday. Only the trawling is automated, which is the part that was never going to survive a busy week anyway.

**2. The keyword list needs to be tight or the scan is worthless.** Tested against the live feed over a 21-day window (205 events):

| Filter setting | Hits |
|---|---|
| Broad categories (`Research`, `Health/Wellness`, `Natural Sciences`) | 82: library tours, farmers markets, mindfulness sessions |
| Tight categories + word-boundary keywords + dedupe | **32**. I&E Fest, Justice in AI, "Should You Start a Startup Now?", MEMS seminars |

The shipped config is the tight one. If Sunday's list ever runs past ~15 rows, cut keywords: don't raise `maxRows`.

**3. Gmail filters only touch new mail.** Nothing retroactively labels your existing inbox. To backfill, search the query in Gmail, select all, apply the label. And the queries in `GMAIL_RULES` are educated guesses at Duke sender domains. I have no way to know your real senders. Revisit them in week 3 and rewrite from what actually arrived.

Filters are set to **label without archiving** (`archiveFilteredMail: false`). Leave it that way until you can recognize these senders on sight. Archiving mail you haven't learned to read yet is how people miss deadlines.

---

## What gets created

**Calendars:** Academic · Work & Projects · Clubs & Duke · Personal · Opportunities

The Opportunities/Clubs split is the one that matters: Opportunities holds things you're *considering*, so your calendar never lies to you about what you've actually committed to.

**Rhythms** (on Personal, with the checklist in the event description)

- Nightly Shutdown: daily, 10 min
- Sunday Weekly Reset: weekly, 45 min
- Monthly Direction Check: first Sunday, 30 min

**Task lists:** Inbox · Academics · Career / Research · Projects · Clubs / Leadership · Personal

**Drive**. `COLLEGE/` with `00 Dashboard` … `99 Archive`, Academics subfoldered by course, plus a **TEMPLATE. Project Home** doc to copy per project.

**COLLEGE DASHBOARD sheet**: five tabs:

- `THIS WEEK`. Big 3, Definition of Done, evidence column, and a *NOT THIS WEEK* section
- `SEMESTER GOALS`: outcome + metric per life area
- `OPPORTUNITIES`: the pipeline, with a status dropdown; also where `duke-scan.gs` writes
- `WEEKLY REVIEWS`: includes a **failure type** dropdown (GOAL / PLAN / EXECUTION) so you diagnose instead of writing "ran out of time"
- `TIME LOG`: estimated vs actual, with per-category multipliers that self-compute after ~3 weeks

That fifth tab wasn't in your four-tab list, but estimated-vs-actual tracking needed somewhere to live, and it's the piece most likely to change how you plan.

---

## The rules the software can't enforce

- **Capacity beats ambition.** Tasks say 15 hours, calendar says 4 delete, delegate, delay, cut scope, or replace. Re-sorting the list is not one of the options.
- **One task system.** Project Home docs describe projects. Google Tasks holds actions. The moment checklists appear in a doc you have two systems, which is zero.
- **Capture in under five seconds**, organize once a day. Sorting at capture time is how the Inbox dies.
- **Time-block one week out, not a semester.** Recurring "Study" blocks three months ahead will be wrong and you'll start ignoring the calendar.
- **Evidence, not vibes.** "2/3: emails to Smith and Patel sent Aug 27" teaches you something. "I should procrastinate less" doesn't.

---

## Undoing it

There's no uninstaller: deleting calendars and Gmail filters by script is more dangerous than useful. By hand: Calendar settings delete calendar; Gmail settings Filters delete; Drive trash the `COLLEGE` folder; Tasks delete list. `resetSeenEvents()` clears only the Duke scan's dedupe memory.
