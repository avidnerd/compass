/**
 * DUKE OPPORTUNITY SCAN
 * ---------------------
 * Duke's event calendar has NO filtered .ics subscription feed — only per-event
 * downloads and RSS/JSON. Subscribing to everything would put ~280 events per
 * month on your calendar, which is exactly the failure mode the funnel exists to
 * prevent.
 *
 * So this does the opposite: every Saturday night it pulls the public JSON feed,
 * keeps only events matching YOUR interest keywords, and appends them to the
 * OPPORTUNITIES tab as DISCOVERED rows.
 *
 * It never writes to your calendar. On Sunday you read a short pre-filtered list
 * and decide what earns a spot on ⭐ Opportunities. The decision stays yours;
 * only the trawling is automated.
 *
 * INSTALL:
 *   1. Paste into the same Apps Script project as setup.gs
 *   2. Edit INTERESTS below — this is the part that matters
 *   3. Run `scanDukeEvents` once manually to check the output
 *   4. Run `installWeeklyScan` to schedule it for Saturdays at 8 PM
 */

const INTERESTS = {
  // An event must hit at least one of these to survive. Matching is whole-word and
  // case-insensitive, against title + description + category — so 'AI' matches "AI"
  // but not "available" or "chair". Prune these in week 3: if Sunday's list runs
  // past ~15 rows, your keywords are too loose, not the cap too low.
  keywords: [
    'artificial intelligence', 'machine learning', 'AI', 'data science',
    'biomedical', 'BME', 'bioengineering', 'medical device',
    'undergraduate research', 'research opportunity', 'fellowship',
    'entrepreneurship', 'startup', 'venture capital',
    'internship', 'career fair', 'recruiting', 'hackathon', 'robotics',
    'Pratt',
  ],

  // Duke's real category taxonomy — these strings are verified against the live
  // feed. Anything not on Duke's list silently never matches, so check before you
  // add: 'Science' does not exist ('Natural Sciences' does).
  //
  // Deliberately kept tight. Adding 'Research' or 'Health/Wellness' back was
  // tested and pulled in library tours, farmers markets, and mindfulness
  // sessions — 82 hits instead of 32. Broad categories are how this becomes noise.
  categories: [
    'Artificial Intelligence', 'Entrepreneurship', 'Engineering', 'Technology',
  ],

  // Hard excludes — these fire before keywords and kill the row outright.
  // Duke's feed is dominated by grand rounds, recitals, and standing exhibits.
  exclude: [
    'Exhibit', 'Visual and Creative Arts', 'Religious/Spiritual',
    'Concert/Music', 'Theater', 'Dance Performance',
    'grand rounds', 'carillon', 'worship',
    'farmers market', 'mindful', 'yoga', 'case conference',
    'town hall', 'library tour',
  ],

  futureDays: 21, // the 2–3 week horizon the weekly scan is meant to cover
  maxRows: 25,    // safety valve; overflow is reported in the log, never silently dropped
};

const FEED_URL = 'https://calendar.duke.edu/events/index.json';
const SEEN_KEY = 'duke_seen_guids';

// ---------------------------------------------------------------------------

function installWeeklyScan() {
  ScriptApp.getProjectTriggers()
    .filter((t) => t.getHandlerFunction() === 'scanDukeEvents')
    .forEach((t) => ScriptApp.deleteTrigger(t));

  ScriptApp.newTrigger('scanDukeEvents')
    .timeBased()
    .onWeekDay(ScriptApp.WeekDay.SATURDAY)
    .atHour(20)
    .create();

  console.log('Weekly Duke scan installed: Saturdays ~8 PM, feeding the OPPORTUNITIES tab.');
}

function scanDukeEvents() {
  const sheet = openOpportunitiesTab();
  if (!sheet) {
    console.log('Could not find the OPPORTUNITIES tab. Run setUp() from setup.gs first.');
    return;
  }

  const events = fetchDukeEvents(INTERESTS.futureDays);
  console.log('feed returned ' + events.length + ' events over ' + INTERESTS.futureDays + ' days');

  const seen = loadSeen();
  const alreadyListed = existingTitles(sheet);

  const keywordRes = INTERESTS.keywords.map(wordMatcher);
  const excludeRes = INTERESTS.exclude.map(wordMatcher);

  const hits = [];
  events.forEach((wrapper) => {
    const e = wrapper.event;
    if (!e || e.status === 'CANCELLED' || e.deleted === 'true') return;
    if (seen[e.guid]) return;

    const cats = categoryValues(e);
    const haystack = [e.summary || '', stripTags(e.description || ''), cats.join(' ')].join(' ');

    if (excludeRes.some((re) => re.test(haystack))) return;

    const kwIndex = keywordRes.findIndex((re) => re.test(haystack));
    const categoryHit = INTERESTS.categories.find((c) => cats.indexOf(c) !== -1);
    if (kwIndex === -1 && !categoryHit) return;
    const keywordHit = kwIndex === -1 ? null : INTERESTS.keywords[kwIndex];

    // Duke publishes each occurrence of a recurring event separately, so one title
    // can appear a dozen times in a single feed. Collapse repeats to one row —
    // you only need to decide about "Mobile Health Assessment" once.
    const title = (e.summary || '').trim();
    const key = title.toLowerCase();
    if (!key || alreadyListed[key]) return;
    alreadyListed[key] = 1;

    hits.push({
      guid: e.guid,
      title: title,
      date: toDate(e.start),
      why: keywordHit ? keywordHit.trim() : categoryHit,
      where: (e.location && e.location.address) || '',
      link: 'https://calendar.duke.edu/?q=' + encodeURIComponent(title),
    });
  });

  hits.sort((a, b) => (a.date && b.date ? a.date - b.date : 0));

  const kept = hits.slice(0, INTERESTS.maxRows);
  const dropped = hits.length - kept.length;

  if (kept.length === 0) {
    console.log('Nothing new matched. Either a quiet week or your keywords are too narrow.');
  } else {
    const rows = kept.map((h) => [
      h.title,
      'Duke event — matched "' + h.why + '"',
      h.date || '',
      '',            // Value — you judge this on Sunday
      '',            // Probability
      'Decide: attend or pass' + (h.where ? '  (' + h.where + ')' : ''),
      'DISCOVERED',
    ]);
    sheet.getRange(sheet.getLastRow() + 1, 1, rows.length, 7).setValues(rows);
    kept.forEach((h) => console.log('  + ' + h.title + '  [' + h.why + ']  ' + h.link));
  }

  if (dropped > 0) {
    console.log('!! ' + dropped + ' further matches were NOT added (maxRows=' +
      INTERESTS.maxRows + '). Tighten INTERESTS.keywords rather than raising the cap.');
  }

  hits.forEach((h) => { seen[h.guid] = 1; });
  saveSeen(seen);
  console.log('added ' + kept.length + ' rows to OPPORTUNITIES');
}

/** Clears the dedupe memory so previously-seen events can reappear. */
function resetSeenEvents() {
  PropertiesService.getUserProperties().deleteProperty(SEEN_KEY);
  console.log('Dedupe memory cleared.');
}

// ---------------------------------------------------------------------------

function fetchDukeEvents(days) {
  const res = UrlFetchApp.fetch(FEED_URL + '?future_days=' + days, {
    muteHttpExceptions: true,
  });
  if (res.getResponseCode() !== 200) {
    throw new Error('Duke feed returned HTTP ' + res.getResponseCode());
  }
  const parsed = JSON.parse(res.getContentText());
  return parsed.events || [];
}

function categoryValues(e) {
  if (!e.categories || !e.categories.category) return [];
  const list = [].concat(e.categories.category);
  return list.map((c) => (c && c.value) || '').filter(String);
}

/** Whole-word, case-insensitive matcher. Keeps 'AI' from matching 'available'. */
function wordMatcher(term) {
  const escaped = String(term).trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp('(^|[^A-Za-z0-9])' + escaped + '($|[^A-Za-z0-9])', 'i');
}

/**
 * Duke's feed gives "20260610T120000" for timed events and a bare "20260823"
 * for all-day ones (Convocation, Drop/Add deadlines, holidays).
 */
function toDate(start) {
  if (!start || !start.unformatted) return '';
  const s = String(start.unformatted);
  const timed = s.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})$/);
  if (timed) return new Date(+timed[1], +timed[2] - 1, +timed[3], +timed[4], +timed[5], +timed[6]);
  const allDay = s.match(/^(\d{4})(\d{2})(\d{2})$/);
  if (allDay) return new Date(+allDay[1], +allDay[2] - 1, +allDay[3]);
  return '';
}

function stripTags(html) {
  return String(html).replace(/<[^>]*>/g, ' ');
}

function openOpportunitiesTab() {
  const files = DriveApp.getFilesByName(CONFIG.dashboardName);
  while (files.hasNext()) {
    const file = files.next();
    if (file.getMimeType() !== MimeType.GOOGLE_SHEETS) continue;
    const tab = SpreadsheetApp.open(file).getSheetByName('OPPORTUNITIES');
    if (tab) return tab;
  }
  return null;
}

function existingTitles(sheet) {
  const last = sheet.getLastRow();
  const map = {};
  if (last < 2) return map;
  sheet.getRange(2, 1, last - 1, 1).getValues().forEach((r) => {
    const v = String(r[0] || '').trim().toLowerCase();
    if (v) map[v] = 1;
  });
  return map;
}

function loadSeen() {
  const raw = PropertiesService.getUserProperties().getProperty(SEEN_KEY);
  try {
    return raw ? JSON.parse(raw) : {};
  } catch (err) {
    return {};
  }
}

function saveSeen(seen) {
  // Properties cap out around 9 KB per value; keep the most recent ~600 guids.
  const keys = Object.keys(seen);
  const trimmed = {};
  keys.slice(Math.max(0, keys.length - 600)).forEach((k) => { trimmed[k] = 1; });
  PropertiesService.getUserProperties().setProperty(SEEN_KEY, JSON.stringify(trimmed));
}
