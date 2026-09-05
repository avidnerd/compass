/**
 * COLLEGE OS — one-time provisioner
 * ---------------------------------
 * Creates, in YOUR Google account:
 *   - 5 Google Calendars (Academic / Work & Projects / Clubs & Duke / Personal / Opportunities)
 *   - 3 recurring rhythm events (nightly shutdown, Sunday reset, monthly review)
 *   - 6 Google Tasks lists (Inbox / Academics / Career / Projects / Clubs / Personal)
 *   - The COLLEGE Drive folder tree + a Project Home template doc
 *   - The COLLEGE DASHBOARD spreadsheet (5 tabs, pre-formatted)
 *   - Gmail label tree + filters
 *
 * Every step is IDEMPOTENT: re-running never creates duplicates.
 *
 * SETUP (see README.md for the full walkthrough):
 *   1. script.google.com -> New project -> paste this file
 *   2. Services (+) -> add "Tasks API" and "Gmail API"  (identifiers must be Tasks and Gmail)
 *   3. Run `setUp`. Approve the OAuth prompt.
 *   4. Read the execution log. It prints the Drive + Sheet links.
 *
 * To undo: run `whatWouldBeCreated()` first if you want a dry run.
 */

// ---------------------------------------------------------------------------
// CONFIG — edit before running
// ---------------------------------------------------------------------------

const CONFIG = {
  // Set false to label mail without pulling it out of the inbox.
  // Leave false for your first few weeks — archiving mail you haven't learned to
  // recognize yet is how people miss things.
  archiveFilteredMail: false,

  // Skip any section you want to set up by hand.
  run: {
    calendars: true,
    rhythms: true,
    taskLists: true,
    drive: true,
    dashboard: true,
    gmail: true,
  },

  driveRoot: 'COLLEGE',
  dashboardName: 'COLLEGE DASHBOARD',

  // Your local timezone rhythms are scheduled in.
  nightlyShutdownHour: 22, // 10:00 PM, 10 min
  weeklyResetHour: 16,     // Sunday 4:00 PM, 45 min
  monthlyReviewHour: 17,   // First Sunday 5:00 PM, 30 min
};

const CALENDARS = [
  { name: 'Academic',        color: CalendarApp.Color.BLUE,   desc: 'Classes, exams, office hours, academic deadlines you must attend.' },
  { name: 'Work & Projects', color: CalendarApp.Color.GREEN,  desc: 'Research, job shifts, startup meetings, scheduled project work.' },
  { name: 'Clubs & Duke',    color: CalendarApp.Color.ORANGE, desc: 'Club meetings, org events, Duke commitments you have accepted.' },
  { name: 'Personal',        color: CalendarApp.Color.MAUVE,  desc: 'Exercise, appointments, social, travel, system rhythms.' },
  { name: 'Opportunities',   color: CalendarApp.Color.YELLOW, desc: 'Events you are CONSIDERING. Nothing here is a commitment yet.' },
];

const TASK_LISTS = [
  'Inbox',
  'Academics',
  'Career / Research',
  'Projects',
  'Clubs / Leadership',
  'Personal',
];

const DRIVE_TREE = {
  '00 Dashboard': [],
  '01 Academics': ['EGR', 'Math', 'Chemistry', 'Writing', 'Other'],
  '02 Research': [],
  '03 Career': [],
  '04 Clubs & Leadership': [],
  '05 Projects & Entrepreneurship': [],
  '06 Personal': [],
  '07 Opportunities': [],
  '99 Archive': [],
};

// Gmail labels + the filter that feeds each one.
// The queries below are STARTING GUESSES based on common Duke senders. You will
// not know your real senders until mail starts arriving — revisit these in week 3
// and rewrite the queries from what actually landed in your inbox.
const GMAIL_RULES = [
  { label: 'Duke', query: null }, // parent only, no filter
  { label: 'Duke/Academic',       query: 'from:(sakai.duke.edu OR canvas.duke.edu OR duke.instructure.com)' },
  { label: 'Duke/Pratt',          query: 'from:(pratt.duke.edu)' },
  { label: 'Duke/Research',       query: 'from:(undergraduateresearch@duke.edu OR ours@duke.edu OR bassconnections@duke.edu)' },
  { label: 'Duke/Career',         query: 'from:(careerhub@duke.edu OR careercenter@duke.edu OR handshake.com)' },
  { label: 'Duke/Clubs',          query: 'from:(dukegroups.com OR campusgroups.com)' },
  { label: 'Duke/Opportunities',  query: 'from:(calendar.duke.edu OR innovate.duke.edu OR entrepreneurship.duke.edu)' },
  { label: 'Duke/Administrative', query: 'from:(bursar@duke.edu OR registrar@duke.edu OR housing@duke.edu OR studentaffairs@duke.edu)' },
];

// ---------------------------------------------------------------------------
// ENTRY POINTS
// ---------------------------------------------------------------------------

function setUp() {
  const log = [];
  const say = (m) => { log.push(m); console.log(m); };

  say('=== COLLEGE OS SETUP ===');

  if (CONFIG.run.calendars) setUpCalendars(say);
  if (CONFIG.run.rhythms) setUpRhythms(say);
  if (CONFIG.run.taskLists) setUpTaskLists(say);

  let root = null;
  if (CONFIG.run.drive) root = setUpDrive(say);
  if (CONFIG.run.dashboard) setUpDashboard(say, root);
  if (CONFIG.run.gmail) setUpGmail(say);

  say('=== DONE ===');
  say('Next: the manual steps in README.md (Tasks lists cannot be reordered by API,');
  say('and Duke calendar subscriptions must be added by hand).');
  return log.join('\n');
}

/** Dry run — prints what does not exist yet without creating anything. */
function whatWouldBeCreated() {
  const missing = [];
  CALENDARS.forEach((c) => {
    if (CalendarApp.getCalendarsByName(c.name).length === 0) missing.push('calendar: ' + c.name);
  });
  const existingLists = (Tasks.Tasklists.list({ maxResults: 100 }).items || []).map((l) => l.title);
  TASK_LISTS.forEach((t) => { if (existingLists.indexOf(t) === -1) missing.push('task list: ' + t); });
  const existingLabels = (Gmail.Users.Labels.list('me').labels || []).map((l) => l.name);
  GMAIL_RULES.forEach((r) => { if (existingLabels.indexOf(r.label) === -1) missing.push('label: ' + r.label); });
  if (!findChildFolder(DriveApp.getRootFolder(), CONFIG.driveRoot)) missing.push('drive folder: ' + CONFIG.driveRoot);
  console.log(missing.length ? missing.join('\n') : 'Everything already exists.');
  return missing;
}

// ---------------------------------------------------------------------------
// CALENDARS
// ---------------------------------------------------------------------------

function setUpCalendars(say) {
  CALENDARS.forEach((spec) => {
    const existing = CalendarApp.getCalendarsByName(spec.name);
    if (existing.length > 0) {
      say('calendar exists: ' + spec.name);
      return;
    }
    const cal = CalendarApp.createCalendar(spec.name, { summary: spec.desc });
    cal.setColor(spec.color);
    cal.setSelected(true);
    say('created calendar: ' + spec.name);
  });
}

function calendarNamed(name) {
  const found = CalendarApp.getCalendarsByName(name);
  return found.length ? found[0] : CalendarApp.getDefaultCalendar();
}

// ---------------------------------------------------------------------------
// RHYTHMS — the recurring events that make the system self-maintaining
// ---------------------------------------------------------------------------

function setUpRhythms(say) {
  const cal = calendarNamed('Personal');
  const tz = Session.getScriptTimeZone();

  ensureSeries(cal, say, {
    title: 'Nightly Shutdown',
    description: [
      '5–10 minutes. Do not let this become a ceremony.',
      '',
      '1. Check tomorrow\'s Calendar.',
      '2. Check overdue Tasks.',
      '3. Process Inbox to zero.',
      '4. Move unfinished Tasks to a real day.',
      '5. Pick tomorrow\'s Top 3.',
      '6. Verify your first commitment tomorrow morning.',
    ].join('\n'),
    start: atHour(nextDay(1), CONFIG.nightlyShutdownHour),
    minutes: 10,
    recurrence: CalendarApp.newRecurrence().addDailyRule(),
  });

  ensureSeries(cal, say, {
    title: 'Sunday Weekly Reset',
    description: [
      '45 protected minutes. This is the load-bearing event in the whole system.',
      '',
      '1. EMPTY THE SYSTEM — Gmail, Tasks Inbox, screenshots, notes, downloads,',
      '   texts containing commitments. Anything actionable becomes a Task.',
      '2. REVIEW LAST WEEK\'S GOALS — for each: result, YES/PARTIAL/NO, evidence,',
      '   why, what changes. The evidence field is the point.',
      '3. DIAGNOSE — was the goal wrong, was the plan wrong, or did I not execute?',
      '   Do not collapse all three into "I ran out of time."',
      '4. SCAN OPPORTUNITIES — Duke Events, DukeGroups, Pratt, Career Center,',
      '   undergrad research, innovation, department newsletters, Gmail labels.',
      '   Only genuinely interesting things go on Opportunities.',
      '5. CHECK DEADLINES — next 3 weeks.',
      '6. PLAN NEXT WEEK — Big 3 + Definition of Done, then time-block the work.',
      '',
      'Capacity rule: if Tasks say 15 hours and Calendar says 4, the Calendar wins.',
      'Delete, delegate, delay, cut scope, or replace something. Do not re-sort the list.',
    ].join('\n'),
    start: atHour(nextWeekday(0), CONFIG.weeklyResetHour),
    minutes: 45,
    recurrence: CalendarApp.newRecurrence().addWeeklyRule().onlyOnWeekday(CalendarApp.Weekday.SUNDAY),
  });

  ensureSeries(cal, say, {
    title: 'Monthly Direction Check',
    description: [
      '30 minutes on top of the weekly reset. Semester-goal altitude.',
      '',
      'Am I spending time where I said I cared?',
      'What commitment should I quit?',
      'What opportunity am I missing?',
      'What should I pursue more aggressively?',
    ].join('\n'),
    start: atHour(nextWeekday(0), CONFIG.monthlyReviewHour),
    minutes: 30,
    // BYMONTHDAY 1-7 intersected with BYDAY=SU is the standard "first Sunday" rule.
    recurrence: CalendarApp.newRecurrence()
      .addMonthlyRule()
      .onlyOnMonthDays([1, 2, 3, 4, 5, 6, 7])
      .onlyOnWeekday(CalendarApp.Weekday.SUNDAY),
  });

  say('rhythms scheduled in timezone: ' + tz);
}

function ensureSeries(cal, say, spec) {
  // Look ahead 60 days for an existing event with this title.
  const horizon = new Date(spec.start.getTime() + 60 * 24 * 3600 * 1000);
  const existing = cal.getEvents(spec.start, horizon, { search: spec.title });
  if (existing.length > 0) {
    say('rhythm exists: ' + spec.title);
    return;
  }
  const end = new Date(spec.start.getTime() + spec.minutes * 60 * 1000);
  const series = cal.createEventSeries(spec.title, spec.start, end, spec.recurrence, {
    description: spec.description,
  });
  series.addPopupReminder(10);
  say('created rhythm: ' + spec.title + ' (' + spec.minutes + ' min)');
}

/** Next occurrence of a weekday, 0 = Sunday. Today counts only if it is still ahead. */
function nextWeekday(dow) {
  const d = new Date();
  const delta = (dow - d.getDay() + 7) % 7;
  d.setDate(d.getDate() + (delta === 0 ? 7 : delta));
  return d;
}

function nextDay(n) {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return d;
}

function atHour(date, hour) {
  const d = new Date(date.getTime());
  d.setHours(hour, 0, 0, 0);
  return d;
}

// ---------------------------------------------------------------------------
// GOOGLE TASKS
// ---------------------------------------------------------------------------

function setUpTaskLists(say) {
  const existing = (Tasks.Tasklists.list({ maxResults: 100 }).items || []).map((l) => l.title);
  TASK_LISTS.forEach((title) => {
    if (existing.indexOf(title) !== -1) {
      say('task list exists: ' + title);
      return;
    }
    Tasks.Tasklists.insert({ title: title });
    say('created task list: ' + title);
  });
  say('NOTE: Tasks list ORDER cannot be set by API. Drag Inbox to the top by hand.');
}

// ---------------------------------------------------------------------------
// DRIVE
// ---------------------------------------------------------------------------

function setUpDrive(say) {
  const root = ensureFolder(DriveApp.getRootFolder(), CONFIG.driveRoot, say);

  Object.keys(DRIVE_TREE).forEach((top) => {
    const folder = ensureFolder(root, top, say);
    DRIVE_TREE[top].forEach((sub) => ensureFolder(folder, sub, say));
  });

  ensureProjectHomeTemplate(root, say);
  say('Drive root: ' + root.getUrl());
  return root;
}

function findChildFolder(parent, name) {
  const it = parent.getFoldersByName(name);
  return it.hasNext() ? it.next() : null;
}

function ensureFolder(parent, name, say) {
  const found = findChildFolder(parent, name);
  if (found) {
    if (say) say('folder exists: ' + name);
    return found;
  }
  const created = parent.createFolder(name);
  if (say) say('created folder: ' + name);
  return created;
}

function ensureProjectHomeTemplate(root, say) {
  const dashboard = ensureFolder(root, '00 Dashboard');
  const name = 'TEMPLATE — Project Home';
  if (dashboard.getFilesByName(name).hasNext()) {
    say('template exists: ' + name);
    return;
  }
  const doc = DocumentApp.create(name);
  const body = doc.getBody();
  body.clear();
  body.appendParagraph('PROJECT HOME: <name>').setHeading(DocumentApp.ParagraphHeading.TITLE);
  body.appendParagraph(
    'Copy this doc for every major ongoing thing: a research lab, a club role, a startup, ' +
    'a competition, the job search, a big academic project.'
  ).setItalic(true);
  body.appendParagraph(
    'RULE: no task checklists in here. Tasks live in Google Tasks. This doc answers ' +
    '"what is this project?" — Tasks answers "what must I do next?" Two task systems ' +
    'means zero task systems.'
  ).setItalic(true);

  ['OBJECTIVE', 'CURRENT STATE', 'NEXT MILESTONE', 'CURRENT PRIORITIES',
   'KEY PEOPLE', 'IMPORTANT LINKS', 'DECISIONS', 'OPEN QUESTIONS', 'NOTES'
  ].forEach((h) => {
    body.appendParagraph(h).setHeading(DocumentApp.ParagraphHeading.HEADING2);
    body.appendParagraph('');
  });

  doc.saveAndClose();
  DriveApp.getFileById(doc.getId()).moveTo(dashboard);
  say('created template: ' + name);
}

// ---------------------------------------------------------------------------
// DASHBOARD SPREADSHEET
// ---------------------------------------------------------------------------

function setUpDashboard(say, root) {
  const parent = root
    ? ensureFolder(root, '00 Dashboard')
    : ensureFolder(ensureFolder(DriveApp.getRootFolder(), CONFIG.driveRoot), '00 Dashboard');

  const existing = parent.getFilesByName(CONFIG.dashboardName);
  if (existing.hasNext()) {
    say('dashboard exists: ' + existing.next().getUrl());
    return;
  }

  const ss = SpreadsheetApp.create(CONFIG.dashboardName);

  buildTab(ss, 'THIS WEEK',
    ['Area', 'Goal', 'Definition of Done', 'Progress', 'Evidence'],
    [
      ['Academics', 'Stay ahead', 'Everything submitted ≥24h early', '', 'Tasks'],
      ['Research', 'Start outreach', '3 emails sent', '', 'Gmail'],
      ['Clubs', 'Explore orgs', 'Attend 3 events', '', 'Calendar'],
      ['Projects', 'Advance prototype', 'Sensor test complete', '', 'Drive'],
      ['Personal', 'Exercise', '3 workouts', '', 'Calendar'],
      [],
      ['THIS WEEK\'S BIG 3'],
      ['1.'], ['2.'], ['3.'],
      [],
      ['NOT THIS WEEK'],
      ['Valuable, deliberately postponed. This section is what keeps the Big 3 to three.'],
    ]);

  buildTab(ss, 'SEMESTER GOALS',
    ['Area', 'Semester outcome', 'Metric / how I would know', 'Status'],
    [
      ['Academic', 'Establish strong academic performance', 'Per-course target', ''],
      ['Research', 'Join a research lab', '≥10 targeted outreach attempts, lab secured', ''],
      ['Career', 'Build professional network', '2 substantive conversations per month', ''],
      ['Clubs', 'Find orgs worth committing to', 'Explore 8, commit deeply to ≤3', ''],
      ['Projects', 'Ship a usable milestone', 'MVP complete', ''],
      ['Social', 'Build real friendships', 'Deliberate recurring social activity', ''],
      ['Music', 'Sustain playing', 'Weekly ensemble attendance', ''],
      ['Personal', 'Sustainable routine', 'Sleep / exercise floor held', ''],
    ]);

  buildTab(ss, 'OPPORTUNITIES',
    ['Opportunity', 'Type', 'Deadline', 'Value', 'Probability', 'Next Action', 'Status'],
    [
      ['AI Lab', 'Research', '', 'High', 'Medium', 'Email professor', 'RESEARCHING'],
      ['Startup competition', 'Entrepreneurship', '', 'Medium', 'High', 'Find teammate', 'DISCOVERED'],
    ],
    (sheet) => {
      const statuses = ['DISCOVERED', 'RESEARCHING', 'APPLYING / ATTENDING', 'WAITING', 'WON / JOINED', 'PASSED / REJECTED'];
      const rule = SpreadsheetApp.newDataValidation().requireValueInList(statuses, true).build();
      sheet.getRange(2, 7, 200, 1).setDataValidation(rule);
      const hiLo = SpreadsheetApp.newDataValidation().requireValueInList(['High', 'Medium', 'Low'], true).build();
      sheet.getRange(2, 4, 200, 2).setDataValidation(hiLo);
      sheet.getRange(2, 3, 200, 1).setNumberFormat('yyyy-mm-dd');
    });

  buildTab(ss, 'WEEKLY REVIEWS',
    ['Week of', 'Goal', 'Result', 'Completed?', 'Evidence', 'Why', 'Failure type', 'Change next week'],
    [
      ['', 'Contact three labs', '2/3', 'PARTIAL', 'Emails to Smith and Patel sent Aug 27',
       'Spent Thursday polishing outreach instead of sending', 'PLAN', 'Cap email drafting at 20 min'],
    ],
    (sheet) => {
      const done = SpreadsheetApp.newDataValidation().requireValueInList(['YES', 'PARTIAL', 'NO'], true).build();
      sheet.getRange(2, 4, 300, 1).setDataValidation(done);
      const kind = SpreadsheetApp.newDataValidation()
        .requireValueInList(['GOAL', 'PLAN', 'EXECUTION'], true).build();
      sheet.getRange(2, 7, 300, 1).setDataValidation(kind);
      sheet.getRange(2, 1, 300, 1).setNumberFormat('yyyy-mm-dd');
    });

  buildTab(ss, 'TIME LOG',
    ['Date', 'Task', 'Category', 'Estimated (min)', 'Actual (min)', 'Ratio'],
    [
      ['', 'Physics problem set', 'Coding', 60, 115, ''],
    ],
    (sheet) => {
      const cats = ['Coding', 'Writing', 'Reading', 'Problem sets', 'Admin', 'Design', 'Other'];
      sheet.getRange(2, 3, 300, 1).setDataValidation(
        SpreadsheetApp.newDataValidation().requireValueInList(cats, true).build());
      sheet.getRange(2, 6, 300, 1).setFormulas(
        Array.from({ length: 300 }, (_, i) => ['=IFERROR(E' + (i + 2) + '/D' + (i + 2) + ',"")']));
      sheet.getRange(2, 6, 300, 1).setNumberFormat('0.00');
      sheet.getRange(2, 1, 300, 1).setNumberFormat('yyyy-mm-dd');
      sheet.getRange(12, 8).setValue('Your personal multipliers (fill in after ~3 weeks):');
      cats.forEach((c, i) => {
        sheet.getRange(13 + i, 8).setValue(c);
        sheet.getRange(13 + i, 9).setFormula(
          '=IFERROR(ROUND(AVERAGEIF($C$2:$C$301,H' + (13 + i) + ',$F$2:$F$301),2),"")');
      });
    });

  // Drop the default sheet Google created.
  const def = ss.getSheetByName('Sheet1');
  if (def) ss.deleteSheet(def);
  ss.setActiveSheet(ss.getSheetByName('THIS WEEK'));

  DriveApp.getFileById(ss.getId()).moveTo(parent);
  say('created dashboard: ' + ss.getUrl());
}

function buildTab(ss, name, headers, rows, decorate) {
  const sheet = ss.getSheetByName(name) || ss.insertSheet(name);
  sheet.getRange(1, 1, 1, headers.length)
    .setValues([headers])
    .setFontWeight('bold')
    .setBackground('#f0f0f0');
  sheet.setFrozenRows(1);

  const width = headers.length;
  const padded = rows.map((r) => {
    const copy = r.slice(0, width);
    while (copy.length < width) copy.push('');
    return copy;
  });
  if (padded.length) sheet.getRange(2, 1, padded.length, width).setValues(padded);

  for (let c = 1; c <= width; c++) sheet.autoResizeColumn(c);
  if (decorate) decorate(sheet);
  return sheet;
}

// ---------------------------------------------------------------------------
// GMAIL
// ---------------------------------------------------------------------------

function setUpGmail(say) {
  const labelIds = {};
  const existing = Gmail.Users.Labels.list('me').labels || [];

  GMAIL_RULES.forEach((rule) => {
    const found = existing.filter((l) => l.name === rule.label)[0];
    if (found) {
      labelIds[rule.label] = found.id;
      say('label exists: ' + rule.label);
      return;
    }
    const created = Gmail.Users.Labels.create({
      name: rule.label,
      labelListVisibility: 'labelShow',
      messageListVisibility: 'show',
    }, 'me');
    labelIds[rule.label] = created.id;
    say('created label: ' + rule.label);
  });

  const currentFilters = (Gmail.Users.Settings.Filters.list('me').filter || []);
  GMAIL_RULES.forEach((rule) => {
    if (!rule.query) return;

    const duplicate = currentFilters.some((f) =>
      f.criteria && f.criteria.query === rule.query);
    if (duplicate) {
      say('filter exists: ' + rule.label);
      return;
    }

    const action = { addLabelIds: [labelIds[rule.label]] };
    if (CONFIG.archiveFilteredMail) action.removeLabelIds = ['INBOX'];

    Gmail.Users.Settings.Filters.create({
      criteria: { query: rule.query },
      action: action,
    }, 'me');
    say('created filter -> ' + rule.label + '  [' + rule.query + ']');
  });

  say('NOTE: filters apply to NEW mail only. To label what is already there, search');
  say('the query in Gmail, select all, and apply the label manually.');
  say('NOTE: these queries are guesses. Rewrite them in week 3 from real senders.');
}
