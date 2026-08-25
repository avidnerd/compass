/**
 * COMPASS BRIDGE — a read-only data plane for Compass, in your own account.
 * ------------------------------------------------------------------------
 * Compass calls this Web App for everything it reads from Google; the script
 * runs as YOU, with YOUR OAuth grant, and costs nothing.
 *
 * DEPLOY THIS AS ITS OWN APPS SCRIPT PROJECT — not alongside setup.gs.
 * That is deliberate: setup.gs needs write scopes to build the College OS,
 * and this bridge must never have them. Its manifest requests ONLY
 * `*.readonly` scopes, so "Compass cannot change anything in your Google
 * account" is enforced by Google's OAuth layer, not merely by this code.
 *
 * SETUP
 *   1. script.google.com -> New project. Name it "Compass Bridge".
 *   2. Paste this file into Code.gs.
 *   3. Project Settings -> check "Show appsscript.json manifest file", then
 *      replace the manifest with bridge/appsscript.json from this repo.
 *   4. Run `setUpBridge`. Approve the OAuth prompt (your own script, so Google
 *      shows the "unverified app" warning -> Advanced -> Go to project).
 *      The execution log prints your bridge token. Copy it.
 *   5. Deploy -> New deployment -> type "Web app".
 *        Execute as:       Me
 *        Who has access:   Anyone
 *      Copy the /exec URL.
 *   6. Paste the URL and the token into Compass: Settings -> Connections.
 *
 * "Who has access: Anyone" is required for a program to call this without a
 * Google login. Nothing is exposed by that alone: every request must carry the
 * token from step 4, and the URL itself is unguessable. Treat the URL + token
 * together as a password. `rotateBridgeToken()` invalidates the old one.
 *
 * Adding a function here that writes is a mistake the manifest will catch —
 * the script has no write scope to grant it.
 */

const TOKEN_KEY = 'COMPASS_BRIDGE_TOKEN';

// Every capability Compass may ask for. A name that is not in this table is
// rejected before anything runs.
const HANDLERS = {
  'bridge.hello': hello,

  'drive.list_files': driveListFiles,
  'drive.search_files': driveListFiles,
  'docs.get_text': docsGetText,
  'sheets.get_values': sheetsGetValues,
  'sheets.get_metadata': sheetsGetMetadata,
  'slides.get_presentation': slidesGetPresentation,

  'calendar.list_events': calendarListEvents,
  'calendar.list_calendars': calendarListCalendars,

  'gmail.list_messages': gmailListMessages,
  'gmail.get_message': gmailGetMessage,

  // Google Tasks — Compass cannot read these yet, so this is new ground.
  // College OS keeps its actions here, which is why the dashboard's "Tasks"
  // evidence rows exist.
  'tasks.list_tasklists': tasksListTaskLists,
  'tasks.list_tasks': tasksListTasks,
};

// Connector -> the capability used to prove the grant still works.
const VALIDATORS = {
  google_drive: 'drive.list_files',
  google_docs: 'drive.list_files',
  google_sheets: 'drive.list_files',
  google_slides: 'drive.list_files',
  google_calendar: 'calendar.list_calendars',
  gmail: 'gmail.list_messages',
  google_tasks: 'tasks.list_tasklists',
};

// ---------------------------------------------------------------------------
// SETUP / OPERATIONS
// ---------------------------------------------------------------------------

/** Generates the bridge token (idempotent) and prints it. Run this first. */
function setUpBridge() {
  const props = PropertiesService.getScriptProperties();
  let token = props.getProperty(TOKEN_KEY);
  if (!token) {
    token = newToken();
    props.setProperty(TOKEN_KEY, token);
    console.log('Created a new bridge token.');
  } else {
    console.log('Bridge token already exists (re-running changed nothing).');
  }
  console.log('');
  console.log('  BRIDGE TOKEN: ' + token);
  console.log('');
  console.log('Next: Deploy -> New deployment -> Web app (Execute as: Me,');
  console.log('Who has access: Anyone). Paste the /exec URL and this token');
  console.log('into Compass under Settings -> Connections.');
  return token;
}

/** Invalidates the current token and issues a new one. */
function rotateBridgeToken() {
  const token = newToken();
  PropertiesService.getScriptProperties().setProperty(TOKEN_KEY, token);
  console.log('Rotated. Update Compass with the new token: ' + token);
  return token;
}

/** Dry run — proves each scope actually works before Compass depends on it. */
function testBridge() {
  Object.keys(VALIDATORS).forEach(function (connector) {
    const capability = VALIDATORS[connector];
    try {
      HANDLERS[capability](defaultProbeArgs(capability));
      console.log('ok      ' + connector + '  (' + capability + ')');
    } catch (err) {
      console.log('FAILED  ' + connector + '  (' + capability + '): ' + err);
    }
  });
  probeSheetsApi();
}

/**
 * The google_sheets validator reads through Drive, so a disabled Sheets API
 * stays hidden until the first real dashboard read fails. Ask the Sheets API
 * about a deliberately invalid id instead: 404 proves it is enabled and
 * reachable, 403 means it still needs switching on in the Cloud project.
 */
function probeSheetsApi() {
  const resp = UrlFetchApp.fetch(
    'https://sheets.googleapis.com/v4/spreadsheets/compass-bridge-probe-not-a-real-id', {
      headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
      muteHttpExceptions: true,
    });
  const code = resp.getResponseCode();
  if (code === 404 || code === 400) {
    console.log('ok      google_sheets  (sheets API reachable)');
  } else if (code === 403) {
    console.log('FAILED  google_sheets  (sheets API): not enabled on this script\'s Cloud ' +
      'project. Enable "Google Sheets API" and re-run.');
  } else {
    console.log('FAILED  google_sheets  (sheets API): unexpected HTTP ' + code);
  }
}

function newToken() {
  const bytes = Utilities.getUuid() + Utilities.getUuid();
  return Utilities.base64EncodeWebSafe(bytes).replace(/=+$/, '').slice(0, 43);
}

// ---------------------------------------------------------------------------
// ENTRY POINT
// ---------------------------------------------------------------------------

function doGet(e) {
  // Apps Script cannot set an HTTP status on a ContentService response, so
  // failures are reported in the body and the client checks for `error`.
  try {
    const params = (e && e.parameter) || {};
    const expected = PropertiesService.getScriptProperties().getProperty(TOKEN_KEY);
    if (!expected) return json({ error: { code: 'bridge_not_set_up', message: 'Run setUpBridge().' } });
    if (!constantTimeEquals(String(params.token || ''), expected)) {
      return json({ error: { code: 'unauthorized', message: 'Bad or missing token.' } });
    }

    const fn = String(params.fn || '');
    const handler = HANDLERS[fn];
    if (!handler) {
      return json({ error: { code: 'capability_unsupported', message: 'Unknown capability: ' + fn } });
    }

    let args = {};
    if (params.args) {
      try {
        args = JSON.parse(params.args);
      } catch (err) {
        return json({ error: { code: 'invalid_arguments', message: 'args must be JSON.' } });
      }
    }
    return json(handler(args || {}));
  } catch (err) {
    return json({ error: { code: 'bridge_error', message: String(err && err.message ? err.message : err) } });
  }
}

/** Length-independent comparison so a wrong token leaks nothing by timing. */
function constantTimeEquals(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function json(payload) {
  return ContentService.createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}

// ---------------------------------------------------------------------------
// GOOGLE REST HELPERS
// ---------------------------------------------------------------------------

function apiGet(url) {
  const resp = UrlFetchApp.fetch(url, {
    headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
    muteHttpExceptions: true,
  });
  const code = resp.getResponseCode();
  if (code >= 400) {
    // Google's body usually says exactly what is wrong ("API has not been used
    // in project ... before or it is disabled"). It can contain account
    // details, so it goes to the owner's own execution log — visible when you
    // run testBridge — and never into the error that crosses the network.
    logApiFailure(code, url, resp.getContentText());
    throw new Error('google_api_' + code);
  }
  return JSON.parse(resp.getContentText());
}

function apiGetRaw(url) {
  const resp = UrlFetchApp.fetch(url, {
    headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
    muteHttpExceptions: true,
  });
  const code = resp.getResponseCode();
  if (code >= 400) {
    logApiFailure(code, url, resp.getContentText());
    throw new Error('google_api_' + code);
  }
  return resp.getContentText();
}

/** Owner-only diagnostics. Never reaches the HTTP response. */
function logApiFailure(code, url, body) {
  console.error('google_api_' + code + ' calling ' + String(url).split('?')[0] +
    '\n  Google said: ' + String(body || '').slice(0, 600));
}

function qs(params) {
  return Object.keys(params)
    .filter(function (k) { return params[k] !== undefined && params[k] !== null && params[k] !== ''; })
    .map(function (k) { return encodeURIComponent(k) + '=' + encodeURIComponent(params[k]); })
    .join('&');
}

/** Google Drive export — plain text for Docs/Slides, CSV for Sheets. */
function driveExport(fileId, mimeType) {
  return apiGetRaw('https://www.googleapis.com/drive/v3/files/' + encodeURIComponent(fileId) +
    '/export?mimeType=' + encodeURIComponent(mimeType));
}

function defaultProbeArgs(capability) {
  if (capability === 'gmail.list_messages') return { maxResults: 1 };
  if (capability === 'drive.list_files') return { page_size: 1 };
  return {};
}

// ---------------------------------------------------------------------------
// HANDLERS
// Response shapes match what Compass already parses: snake_case, with the
// nesting the domain code expects, so no caller has to reshape anything.
// ---------------------------------------------------------------------------

function hello() {
  return {
    ok: true,
    capabilities: Object.keys(HANDLERS),
    timezone: Session.getScriptTimeZone(),
  };
}

function driveListFiles(args) {
  // owned_only drops files other people shared in. Their names and contents
  // reach Compass's prompts, so an install that does not need shared files can
  // remove that input entirely.
  var query = args.owned_only ? "trashed = false and 'me' in owners" : 'trashed = false';
  const payload = apiGet('https://www.googleapis.com/drive/v3/files?' + qs({
    pageSize: Math.min(Number(args.page_size) || 1000, 1000),
    pageToken: args.page_token,
    q: query,
    orderBy: 'modifiedTime desc',
    fields: 'nextPageToken,files(id,name,mimeType,modifiedTime,createdTime,trashed)',
  }));
  return {
    files: (payload.files || []).map(function (f) {
      return {
        id: f.id,
        name: f.name,
        mime_type: f.mimeType,
        modified_time: f.modifiedTime,
        created_time: f.createdTime,
        trashed: !!f.trashed,
      };
    }),
    next_page_token: payload.nextPageToken || null,
  };
}

function docsGetText(args) {
  const id = args.document_id || args.file_id || args.id;
  if (!id) throw new Error('document_id is required');
  return { text: driveExport(id, 'text/plain') };
}

function sheetsGetValues(args) {
  const id = args.spreadsheet_id || args.file_id || args.id;
  if (!id) throw new Error('spreadsheet_id is required');
  const range = args.range || args.sheet_name;

  if (!range) {
    // No range asked for (the interest scan does this) — the first sheet as CSV
    // is both cheap and enough.
    const csv = driveExport(id, 'text/csv');
    return { values: csv ? Utilities.parseCsv(csv) : [] };
  }
  const payload = apiGet('https://sheets.googleapis.com/v4/spreadsheets/' +
    encodeURIComponent(id) + '/values/' + encodeURIComponent(range));
  return { values: payload.values || [], range: payload.range || range };
}

function sheetsGetMetadata(args) {
  const id = args.spreadsheet_id || args.file_id || args.id;
  if (!id) throw new Error('spreadsheet_id is required');
  const payload = apiGet('https://sheets.googleapis.com/v4/spreadsheets/' +
    encodeURIComponent(id) + '?fields=properties.title,sheets.properties.title');
  return {
    title: (payload.properties || {}).title || '',
    sheets: (payload.sheets || []).map(function (s) { return { title: (s.properties || {}).title || '' }; }),
  };
}

function slidesGetPresentation(args) {
  const id = args.presentation_id || args.file_id || args.id;
  if (!id) throw new Error('presentation_id is required');
  // Exported text, split into short lines. Compass walks this for keywords and
  // ignores strings longer than ~500 chars, so one giant blob would be useless.
  const lines = driveExport(id, 'text/plain')
    .split('\n')
    .map(function (l) { return l.trim(); })
    .filter(function (l) { return l.length > 2 && l.length < 500; })
    .slice(0, 200);
  return { slides: lines };
}

function calendarListEvents(args) {
  const calendarId = args.calendar_id || 'primary';
  const payload = apiGet('https://www.googleapis.com/calendar/v3/calendars/' +
    encodeURIComponent(calendarId) + '/events?' + qs({
      maxResults: Math.min(Number(args.max_results) || 2500, 2500),
      timeMin: args.time_min,
      timeMax: args.time_max,
      singleEvents: args.single_events === false ? 'false' : 'true',
      orderBy: args.order_by === 'startTime' ? 'startTime' : undefined,
    }));
  return {
    events: {
      items: (payload.items || []).map(function (ev) {
        return {
          id: ev.id,
          summary: ev.summary || '',
          // All-day events carry `date`, not `dateTime`. Leaving date_time null
          // is honest: Compass compares timestamps and a bare date would lie.
          start: { date_time: (ev.start || {}).dateTime || null, date: (ev.start || {}).date || null },
          end: { date_time: (ev.end || {}).dateTime || null, date: (ev.end || {}).date || null },
          status: ev.status || null,
        };
      }),
    },
  };
}

function calendarListCalendars(args) {
  const payload = apiGet('https://www.googleapis.com/calendar/v3/users/me/calendarList?' + qs({
    maxResults: Math.min(Number(args.max_results) || 250, 250),
  }));
  return {
    calendars: (payload.items || []).map(function (c) {
      return { id: c.id, summary: c.summary || '', primary: !!c.primary };
    }),
  };
}

function gmailListMessages(args) {
  const payload = apiGet('https://gmail.googleapis.com/gmail/v1/users/me/messages?' + qs({
    q: args.q,
    maxResults: Math.min(Number(args.maxResults || args.max_results) || 25, 200),
  }));
  return {
    messages: (payload.messages || []).map(function (m) { return { id: m.id, thread_id: m.threadId }; }),
    result_size_estimate: payload.resultSizeEstimate || 0,
  };
}

function gmailGetMessage(args) {
  const id = args.message_id || args.id;
  if (!id) throw new Error('message_id is required');
  // Metadata only: headers and the snippet Gmail itself shows. Never the body.
  const payload = apiGet('https://gmail.googleapis.com/gmail/v1/users/me/messages/' +
    encodeURIComponent(id) + '?format=metadata' +
    '&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date');
  return {
    id: payload.id,
    snippet: payload.snippet || '',
    payload: { headers: ((payload.payload || {}).headers || []) },
  };
}

function tasksListTaskLists() {
  const payload = apiGet('https://tasks.googleapis.com/tasks/v1/users/@me/lists?maxResults=100');
  return {
    task_lists: (payload.items || []).map(function (l) { return { id: l.id, title: l.title }; }),
  };
}

function tasksListTasks(args) {
  const listId = args.task_list_id;
  if (!listId) throw new Error('task_list_id is required');
  const payload = apiGet('https://tasks.googleapis.com/tasks/v1/lists/' +
    encodeURIComponent(listId) + '/tasks?' + qs({
      maxResults: Math.min(Number(args.max_results) || 100, 100),
      showCompleted: 'true',
      showHidden: 'true',
      completedMin: args.completed_min,
      dueMin: args.due_min,
    }));
  return {
    tasks: (payload.items || []).map(function (t) {
      return {
        id: t.id,
        title: t.title || '',
        status: t.status || '',
        due: t.due || null,
        completed_at: t.completed || null,
        updated_at: t.updated || null,
      };
    }),
  };
}
