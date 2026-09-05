"""College OS bridge.

College OS (`college-os/`) is an Apps Script provisioner that builds a Google
Workspace operating system in the user's own account: the COLLEGE Drive tree,
the COLLEGE DASHBOARD spreadsheet (THIS WEEK / SEMESTER GOALS / OPPORTUNITIES /
WEEKLY REVIEWS / TIME LOG), five calendars, six Tasks lists, and Gmail labels.

Compass already reads Google Workspace read-only through the bridge, so this module
teaches it to recognise that structure and turn it into first-class product
objects:

  * SEMESTER GOALS / THIS WEEK Big 3 / OPPORTUNITIES rows  -> Compass quests
  * the sheet's own "Evidence" column                      -> evidence specs
  * WEEKLY REVIEWS                                         -> honesty metrics
  * TIME LOG                                               -> estimate calibration

Privacy rules inherited from the rest of the app:
  * Compass is read-only by construction. Nothing here writes to the sheet, the
    calendars, Tasks, Drive, or Gmail — the write-verb denylist in
    `capabilities.py` makes that structurally impossible.
  * Dashboard CELL CONTENT is file content, so it is fetched with
    `ttl_seconds=None` (uncached) and memoised in process memory only. What
    lands in SQLite is the link (file ids) and the import ledger, plus whatever
    quest text the user explicitly chose to import.
"""
import json
import logging
import re
import time
from datetime import timedelta

from .. import capabilities, db, events, telemetry
from ..config import settings
from ..errors import ApiError
from ..util import now, now_iso, parse_iso, sha256_hex

logger = logging.getLogger("compass.college")

# ---------------------------------------------------------------- constants
# These mirror college-os/setup.gs. Keep them in sync with that file.

TAB_THIS_WEEK = "THIS WEEK"
TAB_SEMESTER = "SEMESTER GOALS"
TAB_OPPORTUNITIES = "OPPORTUNITIES"
TAB_REVIEWS = "WEEKLY REVIEWS"
TAB_TIME_LOG = "TIME LOG"
TABS = [TAB_THIS_WEEK, TAB_SEMESTER, TAB_OPPORTUNITIES, TAB_REVIEWS, TAB_TIME_LOG]

CALENDAR_NAMES = [
    "Academic", "Work & Projects", "Clubs & Duke", "Personal", "Opportunities",
]
RHYTHM_TITLES = ["Nightly Shutdown", "Sunday Weekly Reset", "Monthly Direction Check"]
TASK_LIST_NAMES = [
    "Inbox", "Academics", "Career / Research", "Projects",
    "Clubs / Leadership", "Personal",
]


def normalise_name(name: str) -> str:
    """Compare Workspace object names ignoring a leading decorative prefix.

    Earlier versions of the provisioner prefixed calendars and task lists with
    an emoji. Accounts set up then still carry those names, so matching strips
    any leading non-alphanumeric characters before comparing.
    """
    return re.sub(r"^[^0-9A-Za-z]+", "", name or "").strip().casefold()

OPPORTUNITY_STATUSES = [
    "DISCOVERED", "RESEARCHING", "APPLYING / ATTENDING", "WAITING",
    "WON / JOINED", "PASSED / REJECTED",
]
OPEN_OPPORTUNITY_STATUSES = {"DISCOVERED", "RESEARCHING", "APPLYING / ATTENDING", "WAITING"}
FAILURE_TYPES = ["GOAL", "PLAN", "EXECUTION"]

GOOGLE_FOLDER = "application/vnd.google-apps.folder"

# The dashboard's own "Evidence" column already says how the user would prove a
# goal. Map that vocabulary onto Compass's evidence enums.
_EVIDENCE_HINTS: list[tuple[str, list[str]]] = [
    ("github", ["github_commit_created", "github_pull_request_merged"]),
    ("commit", ["github_commit_created"]),
    ("pull request", ["github_pull_request_merged"]),
    ("pr ", ["github_pull_request_merged"]),
    ("code", ["github_commit_created"]),
    ("gmail", ["email_sent"]),
    ("email", ["email_sent"]),
    ("outreach", ["email_sent"]),
    ("calendar", ["calendar_event_completed"]),
    ("attend", ["calendar_event_completed"]),
    ("meet", ["meet_attended"]),
    ("slide", ["presentation_content_changed"]),
    ("deck", ["presentation_content_changed"]),
    ("sheet", ["sheet_values_changed"]),
    ("spreadsheet", ["sheet_values_changed"]),
    ("doc", ["document_content_changed", "file_modified"]),
    ("write", ["document_content_changed"]),
    ("drive", ["file_created", "file_modified"]),
    ("file", ["file_created", "file_modified"]),
]
# Google Tasks is not one of Compass's eight connectors, so a "Tasks" evidence
# cell honestly degrades to manual confirmation rather than pretending.
_MANUAL_ONLY_HINTS = ("task", "tasks", "self", "manual", "vibes")


def evidence_specs_for(evidence_cell: str, available: list[str]) -> list[str]:
    """Translate a dashboard Evidence cell into allowed Compass evidence specs."""
    text = (evidence_cell or "").strip().lower()
    picked: list[str] = []
    if text and not any(h in text for h in _MANUAL_ONLY_HINTS):
        for needle, specs in _EVIDENCE_HINTS:
            if needle in text:
                picked.extend(s for s in specs if s not in picked)
    allowed = [s for s in picked if s in available][:3]
    return allowed or ["manual_confirmation"]


# ------------------------------------------------------------------ parsing

_APOSTROPHES = str.maketrans({"‘": "'", "’": "'", "ʼ": "'"})


def _norm(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _key(tab: str, *parts: str) -> str:
    material = "|".join(p.lower() for p in parts if p)
    return f"{tab.lower().replace(' ', '_')}:{sha256_hex(material)[:16]}"


def _rows_from_payload(payload) -> list[list[str]]:
    """Tolerant row extraction — sheet responses differ in envelope shape."""
    if not isinstance(payload, dict):
        return []
    for key in ("values", "rows", "data"):
        candidate = payload.get(key)
        if isinstance(candidate, list) and candidate and isinstance(candidate[0], list):
            return [[_norm(c) for c in row] for row in candidate]
        if isinstance(candidate, dict):
            nested = _rows_from_payload(candidate)
            if nested:
                return nested
    for key in ("value_ranges", "valueRanges", "sheets", "ranges"):
        candidate = payload.get(key)
        if isinstance(candidate, list):
            for entry in candidate:
                nested = _rows_from_payload(entry)
                if nested:
                    return nested
    return []


def _cell(row: list[str], index: int) -> str:
    return row[index] if index < len(row) else ""


def parse_this_week(rows: list[list[str]]) -> dict:
    """Areas table + Big 3 + the NOT THIS WEEK list."""
    areas: list[dict] = []
    big3: list[dict] = []
    not_this_week: list[str] = []
    section = "areas"
    for row in rows[1:]:
        first = _cell(row, 0).translate(_APOSTROPHES)
        upper = first.upper()
        if not any(_norm(c) for c in row):
            continue
        if upper.startswith("THIS WEEK'S BIG 3"):
            section = "big3"
            continue
        if upper.startswith("NOT THIS WEEK"):
            section = "not_this_week"
            continue
        if section == "areas":
            goal = _cell(row, 1)
            if not first or not goal:
                continue
            areas.append({
                "area": first, "goal": goal,
                "definition_of_done": _cell(row, 2),
                "progress": _cell(row, 3),
                "evidence": _cell(row, 4),
                "source_key": _key(TAB_THIS_WEEK, "area", first, goal),
            })
        elif section == "big3":
            text = re.sub(r"^\d+\s*[.)]\s*", "", first).strip()
            if not text:
                continue
            big3.append({"text": text, "source_key": _key(TAB_THIS_WEEK, "big3", text)})
        else:
            if first:
                not_this_week.append(first)
    return {"areas": areas, "big_three": big3, "not_this_week": not_this_week}


def parse_semester_goals(rows: list[list[str]]) -> list[dict]:
    out: list[dict] = []
    for row in rows[1:]:
        area, outcome = _cell(row, 0), _cell(row, 1)
        if not area or not outcome:
            continue
        out.append({
            "area": area, "outcome": outcome,
            "metric": _cell(row, 2), "status": _cell(row, 3),
            "source_key": _key(TAB_SEMESTER, area, outcome),
        })
    return out


def parse_opportunities(rows: list[list[str]]) -> list[dict]:
    out: list[dict] = []
    for row in rows[1:]:
        title = _cell(row, 0)
        if not title:
            continue
        status = _cell(row, 6).upper() or "DISCOVERED"
        out.append({
            "title": title, "type": _cell(row, 1), "deadline": _cell(row, 2),
            "value": _cell(row, 3), "probability": _cell(row, 4),
            "next_action": _cell(row, 5), "status": status,
            "open": status in OPEN_OPPORTUNITY_STATUSES,
            "source_key": _key(TAB_OPPORTUNITIES, title),
        })
    out.sort(key=lambda o: (not o["open"], o["deadline"] or "9999", o["title"]))
    return out


def parse_weekly_reviews(rows: list[list[str]]) -> dict:
    """The honesty tab: did goals land, and when they didn't, why."""
    entries: list[dict] = []
    for row in rows[1:]:
        goal = _cell(row, 1)
        if not goal:
            continue
        entries.append({
            "week_of": _cell(row, 0), "goal": goal, "result": _cell(row, 2),
            "completed": _cell(row, 3).upper(), "evidence": _cell(row, 4),
            "why": _cell(row, 5), "failure_type": _cell(row, 6).upper(),
            "change_next_week": _cell(row, 7),
        })
    outcomes = {k: 0 for k in ("YES", "PARTIAL", "NO")}
    failures = {k: 0 for k in FAILURE_TYPES}
    with_evidence = 0
    for e in entries:
        if e["completed"] in outcomes:
            outcomes[e["completed"]] += 1
        if e["failure_type"] in failures:
            failures[e["failure_type"]] += 1
        if e["evidence"]:
            with_evidence += 1
    total = len(entries)
    return {
        "entries": entries[-12:],
        "total": total,
        "outcomes": outcomes,
        "failure_types": failures,
        # "Evidence, not vibes" — the share of reviewed goals that cited proof.
        "evidence_rate": round(with_evidence / total, 2) if total else None,
        "dominant_failure": (max(failures, key=lambda k: failures[k])
                             if any(failures.values()) else None),
    }


def _to_float(value: str) -> float | None:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def parse_time_log(rows: list[list[str]], min_samples: int = 3) -> dict:
    """Estimated-vs-actual multipliers, recomputed rather than trusted."""
    buckets: dict[str, list[float]] = {}
    samples = 0
    for row in rows[1:]:
        category = _cell(row, 2) or "Other"
        estimated, actual = _to_float(_cell(row, 3)), _to_float(_cell(row, 4))
        if not estimated or estimated <= 0 or actual is None or actual <= 0:
            continue
        buckets.setdefault(category, []).append(actual / estimated)
        samples += 1
    multipliers = [
        {"category": cat, "multiplier": round(sum(v) / len(v), 2), "samples": len(v),
         "confident": len(v) >= min_samples}
        for cat, v in sorted(buckets.items())
    ]
    all_ratios = [r for v in buckets.values() for r in v]
    return {
        "samples": samples,
        "multipliers": multipliers,
        "overall_multiplier": round(sum(all_ratios) / len(all_ratios), 2) if all_ratios else None,
        "min_samples": min_samples,
    }


_PARSERS = {
    TAB_THIS_WEEK: parse_this_week,
    TAB_SEMESTER: parse_semester_goals,
    TAB_OPPORTUNITIES: parse_opportunities,
    TAB_REVIEWS: parse_weekly_reviews,
    TAB_TIME_LOG: parse_time_log,
}


# -------------------------------------------------------------- link record

def public_link(row: dict | None) -> dict:
    if row is None:
        return {"status": "not_detected", "dashboard_file_id": None, "root_folder_id": None,
                "calendars": [], "detected_at": None, "last_synced_at": None,
                "project_home_count": 0}
    out = dict(row)
    out.pop("profile_id", None)
    out["calendars"] = json.loads(out.pop("calendars_json") or "[]")
    return out


async def get_link(profile_id: str) -> dict | None:
    cur = await db.get().execute("SELECT * FROM college_links WHERE profile_id = ?", (profile_id,))
    row = await cur.fetchone()
    return dict(row) if row else None


async def _store_link(profile_id: str, fields: dict) -> dict:
    ts = now_iso()
    await db.get().execute(
        """INSERT INTO college_links (profile_id, status, root_folder_id, root_folder_name,
             dashboard_file_id, dashboard_name, dashboard_modified_time, project_home_count,
             calendars_json, detected_at, last_synced_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(profile_id) DO UPDATE SET
             status = excluded.status, root_folder_id = excluded.root_folder_id,
             root_folder_name = excluded.root_folder_name,
             dashboard_file_id = excluded.dashboard_file_id,
             dashboard_name = excluded.dashboard_name,
             dashboard_modified_time = excluded.dashboard_modified_time,
             project_home_count = excluded.project_home_count,
             calendars_json = excluded.calendars_json, detected_at = excluded.detected_at,
             last_synced_at = excluded.last_synced_at,
             version = college_links.version + 1, updated_at = excluded.updated_at""",
        (profile_id, fields["status"], fields.get("root_folder_id"), fields.get("root_folder_name"),
         fields.get("dashboard_file_id"), fields.get("dashboard_name"),
         fields.get("dashboard_modified_time"), fields.get("project_home_count") or 0,
         json.dumps(fields.get("calendars") or []), fields.get("detected_at") or ts,
         fields.get("last_synced_at"), ts))
    await db.get().commit()
    return await get_link(profile_id)


async def unlink(profile_id: str) -> dict:
    """Forget the College OS link and import ledger. Never touches the sheet."""
    forget_memo(profile_id)
    await db.get().execute("DELETE FROM college_imports WHERE profile_id = ?", (profile_id,))
    await db.get().execute("DELETE FROM college_links WHERE profile_id = ?", (profile_id,))
    await db.get().commit()
    return {"unlinked": True}


# ---------------------------------------------------------------- detection

async def _list_calendars(profile: dict) -> list[dict]:
    reg = capabilities.current_registry()
    if reg is None or reg.resolve("calendar.list_calendars") is None:
        return []
    try:
        payload, _ = await telemetry.call_capability(
            profile, "calendar.list_calendars", {"max_results": 250},
            ttl_seconds=settings.ttl_calendar_events, connector="google_calendar",
            serve_stale_on_error=True)
    except Exception as exc:
        logger.info("[college] calendar listing unavailable: %s", type(exc).__name__)
        return []
    raw = None
    for key in ("calendars", "items", "calendar_list"):
        value = payload.get(key) if isinstance(payload, dict) else None
        if isinstance(value, dict):
            value = value.get("items")
        if isinstance(value, list):
            raw = value
            break
    out = []
    for entry in raw or []:
        if not isinstance(entry, dict):
            continue
        name = _norm(entry.get("summary") or entry.get("name") or entry.get("title"))
        if name:
            out.append({"name": name, "id": entry.get("id")})
    return out


async def detect(profile: dict, force: bool = False) -> dict:
    """Find the College OS artefacts in the connected Drive/Calendar account.

    Uses only file/calendar METADATA (names, ids, timestamps) — the same data
    the interest scan already lists — so this call is cheap and cacheable.
    """
    files, _meta = await telemetry.list_drive_files(profile, force=force, serve_stale_on_error=True)
    dashboard_name = settings.college_dashboard_name.strip().lower()
    root_name = settings.college_root_folder.strip().lower()

    dashboards, roots, project_homes = [], [], 0
    for f in files:
        if f.get("trashed"):
            continue
        name = _norm(f.get("name"))
        lowered = name.lower()
        mime = f.get("mime_type")
        if lowered == dashboard_name and mime == telemetry.GOOGLE_SHEET:
            dashboards.append(f)
        elif lowered == root_name and mime == GOOGLE_FOLDER:
            roots.append(f)
        elif mime == telemetry.GOOGLE_DOC and lowered.startswith("project home"):
            project_homes += 1

    dashboards.sort(key=lambda f: f.get("modified_time") or "", reverse=True)
    dashboard = dashboards[0] if dashboards else None
    root = roots[0] if roots else None

    present = {normalise_name(c["name"]) for c in await _list_calendars(profile)}
    calendars = ([{"name": n, "present": normalise_name(n) in present} for n in CALENDAR_NAMES]
                 if present else [])

    status = "linked" if dashboard else ("partial" if root else "not_detected")
    # A re-detect may point at a different (or no longer existing) spreadsheet;
    # drop whatever the previous one had in memory.
    forget_memo(profile["id"])
    link = await _store_link(profile["id"], {
        "status": status,
        "root_folder_id": (root or {}).get("id"),
        "root_folder_name": _norm((root or {}).get("name")) or None,
        "dashboard_file_id": (dashboard or {}).get("id"),
        "dashboard_name": _norm((dashboard or {}).get("name")) or None,
        "dashboard_modified_time": (dashboard or {}).get("modified_time"),
        "project_home_count": project_homes,
        "calendars": calendars,
        "detected_at": now_iso(),
        "last_synced_at": (await get_link(profile["id"]) or {}).get("last_synced_at"),
    })
    if status != "not_detected":
        await events.publish("profile", profile["id"], "connection.updated", profile["id"],
                             {"reason": "college_os_detected", "status": status})
    return public_link(link)


# --------------------------------------------------------- dashboard reading
# Cell content is file content: fetched uncached, memoised in memory only.

_memo: dict[str, tuple[float, dict]] = {}
# Sheet reads disagree on how a tab is addressed; remember what worked.
_range_shape: str | None = None


def forget_memo(profile_id: str | None = None) -> None:
    """Drop in-memory dashboard content (profile deletion, cache clear)."""
    if profile_id is None:
        _memo.clear()
    else:
        _memo.pop(profile_id, None)


# A sheet tool that ignores the range argument would hand every tab the same
# rows, which would then be parsed as the wrong thing. Each tab's header row
# carries at least one token no other tab has — require one before trusting it.
_TAB_SIGNATURES = {
    TAB_THIS_WEEK: ("definition of done", "evidence"),
    TAB_SEMESTER: ("semester outcome", "metric"),
    TAB_OPPORTUNITIES: ("opportunity", "probability", "next action"),
    TAB_REVIEWS: ("week of", "failure type", "change next week"),
    TAB_TIME_LOG: ("estimated", "actual", "ratio"),
}


def _is_tab(tab: str, rows: list[list[str]]) -> bool:
    if not rows:
        return False
    header = " | ".join(c.lower() for c in rows[0])
    return any(token in header for token in _TAB_SIGNATURES[tab])


def _range_arguments(spreadsheet_id: str, tab: str, shape: str) -> dict:
    if shape == "a1":
        return {"spreadsheet_id": spreadsheet_id, "range": f"'{tab}'!A1:J400"}
    if shape == "tab":
        return {"spreadsheet_id": spreadsheet_id, "range": tab}
    return {"spreadsheet_id": spreadsheet_id, "sheet_name": tab}


async def _read_tab(profile: dict, spreadsheet_id: str, tab: str) -> list[list[str]]:
    global _range_shape
    shapes = [_range_shape] if _range_shape else []
    shapes += [s for s in ("a1", "tab", "sheet_name") if s != _range_shape]
    for shape in shapes:
        try:
            payload, _ = await telemetry.call_capability(
                profile, "sheets.get_values", _range_arguments(spreadsheet_id, tab, shape),
                ttl_seconds=None, connector="google_sheets")
        except ApiError:
            raise
        except Exception as exc:
            logger.info("[college] tab %s read failed (%s): %s", tab, shape, type(exc).__name__)
            continue
        rows = _rows_from_payload(payload)
        if _is_tab(tab, rows):
            _range_shape = shape
            return rows
        if rows:
            logger.info("[college] %s read returned rows that are not that tab (%s)", tab, shape)
    return []


async def read_dashboard(profile: dict, force: bool = False) -> dict:
    """Parsed dashboard tabs. Raw rows never leave this function."""
    link = await get_link(profile["id"])
    if not link or not link.get("dashboard_file_id"):
        raise ApiError(409, "college_not_linked",
                       "No COLLEGE DASHBOARD found yet. Run detection first.")
    reg = capabilities.current_registry()
    if reg is None or reg.resolve("sheets.get_values") is None:
        raise ApiError(503, "capability_unsupported",
                       "Google Sheets reading is not available on this connection.")

    memo = _memo.get(profile["id"])
    if memo and not force and time.monotonic() - memo[0] < settings.college_dashboard_memo_seconds:
        return memo[1]

    sections: dict = {}
    missing: list[str] = []
    for tab in TABS:
        rows = await _read_tab(profile, link["dashboard_file_id"], tab)
        if not rows:
            missing.append(tab)
            continue
        sections[tab] = _PARSERS[tab](rows)

    result = {
        "sections": sections,
        "missing_tabs": missing,
        "dashboard_file_id": link["dashboard_file_id"],
        "read_at": now_iso(),
    }
    _memo[profile["id"]] = (time.monotonic(), result)
    await db.get().execute(
        "UPDATE college_links SET last_synced_at = ?, updated_at = ? WHERE profile_id = ?",
        (result["read_at"], result["read_at"], profile["id"]))
    await db.get().commit()
    return result


# ----------------------------------------------------------------- importing

async def _imports(profile_id: str) -> dict[str, dict]:
    cur = await db.get().execute(
        "SELECT c.*, q.state AS quest_state FROM college_imports c"
        " LEFT JOIN quests q ON q.id = c.quest_id WHERE c.profile_id = ?", (profile_id,))
    return {r["source_key"]: dict(r) for r in await cur.fetchall()}


def _next_sunday_iso() -> str:
    today = now()
    return (today + timedelta(days=(6 - today.weekday()) % 7 or 7)).date().isoformat()


def _normalize_deadline(value: str) -> str | None:
    text = _norm(value)
    if not text:
        return None
    match = re.search(r"\d{4}-\d{2}-\d{2}", text)
    if match:
        return match.group(0)
    try:
        return parse_iso(text).date().isoformat()
    except ValueError:
        return None


def importable(dashboard: dict, available_evidence: list[str]) -> dict[str, dict]:
    """Every dashboard row Compass can turn into a quest, keyed by source_key."""
    sections = dashboard.get("sections") or {}
    out: dict[str, dict] = {}

    this_week = sections.get(TAB_THIS_WEEK) or {}
    for area in this_week.get("areas", []):
        criterion = area["definition_of_done"] or "You judge that this week's goal was met."
        out[area["source_key"]] = {
            "source_key": area["source_key"], "tab": TAB_THIS_WEEK, "area": area["area"],
            "title": area["goal"],
            "meaning": (f"This week's {area['area']} goal from my College OS weekly plan. "
                        f"Definition of done: {criterion}"),
            "acceptance_criterion": criterion,
            "target_date": _next_sunday_iso(),
            "evidence_specs": evidence_specs_for(area["evidence"], available_evidence),
        }
    for item in this_week.get("big_three", []):
        out[item["source_key"]] = {
            "source_key": item["source_key"], "tab": TAB_THIS_WEEK, "area": "Big 3",
            "title": item["text"],
            "meaning": "One of this week's Big 3 from my College OS weekly plan.",
            "acceptance_criterion": "You judge that this Big 3 item is finished.",
            "target_date": _next_sunday_iso(),
            "evidence_specs": ["manual_confirmation"],
        }
    for goal in sections.get(TAB_SEMESTER) or []:
        metric = goal["metric"] or "You judge that the semester outcome was reached."
        out[goal["source_key"]] = {
            "source_key": goal["source_key"], "tab": TAB_SEMESTER, "area": goal["area"],
            "title": goal["outcome"],
            "meaning": (f"A {goal['area']} outcome from my College OS semester goals. "
                        f"I'll know it's done when: {metric}"),
            "acceptance_criterion": metric,
            "target_date": None,
            "evidence_specs": evidence_specs_for(metric, available_evidence),
        }
    for opp in sections.get(TAB_OPPORTUNITIES) or []:
        if not opp["open"]:
            continue
        action = opp["next_action"] or "Decide whether to pursue this."
        out[opp["source_key"]] = {
            "source_key": opp["source_key"], "tab": TAB_OPPORTUNITIES,
            "area": opp["type"] or "Opportunity",
            "title": f"Pursue: {opp['title']}",
            "meaning": (f"An opportunity from my College OS pipeline (status {opp['status']}). "
                        f"Next action: {action}"),
            "acceptance_criterion": action,
            "target_date": _normalize_deadline(opp["deadline"]),
            "evidence_specs": evidence_specs_for(f"{opp['type']} {action}", available_evidence),
        }
    return out


async def import_rows(profile: dict, source_keys: list[str], plan: bool = True) -> dict:
    """Create Compass quests from dashboard rows, idempotently by source_key.

    The row is re-read server-side from the sheet, so an imported quest always
    matches what the dashboard actually says.
    """
    from . import quests as quest_service

    if not source_keys:
        raise ApiError(422, "invalid_request", "Select at least one row to import.")
    dashboard = await read_dashboard(profile)
    candidates = importable(dashboard, quest_service.available_evidence_types())
    already = await _imports(profile["id"])

    created, skipped, unknown = [], [], []
    for source_key in source_keys[:20]:
        if source_key in already and already[source_key].get("quest_id"):
            skipped.append({"source_key": source_key, "quest_id": already[source_key]["quest_id"]})
            continue
        draft = candidates.get(source_key)
        if draft is None:
            unknown.append(source_key)
            continue
        quest = await quest_service.create_quest(profile["id"], {
            "goal": draft["title"],
            "meaning": draft["meaning"],
            "target_date": draft["target_date"],
            "plan": plan,
            "targets": {"college_os": {
                "source_key": draft["source_key"], "tab": draft["tab"], "area": draft["area"],
                "acceptance_criterion": draft["acceptance_criterion"],
                "evidence_specs": draft["evidence_specs"],
            }},
        })
        await db.get().execute(
            """INSERT INTO college_imports (profile_id, source_key, tab, area, title, quest_id, imported_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(profile_id, source_key) DO UPDATE SET
                 quest_id = excluded.quest_id, imported_at = excluded.imported_at""",
            (profile["id"], draft["source_key"], draft["tab"], draft["area"],
             draft["title"][:200], quest["id"], now_iso()))
        await db.get().commit()
        created.append({"source_key": draft["source_key"], "quest_id": quest["id"],
                        "goal": quest["goal"]})

    return {"created": created, "skipped": skipped, "unknown": unknown}


# ------------------------------------------------------------------ overview

async def overview(profile: dict, force: bool = False) -> dict:
    """Everything the College page needs in one call."""
    from . import quests as quest_service

    link = await get_link(profile["id"])
    if link is None or (force and link.get("status") != "linked"):
        await detect(profile, force=force)
        link = await get_link(profile["id"])
    public = public_link(link)

    if public["status"] != "linked":
        # Two very different failures reach this point. Telling someone to run a
        # provisioner when Compass cannot see their Drive at all sends them to
        # the wrong place, so name the actual blocker.
        from .. import providers as provider_service
        connected = await provider_service.active_provider(profile) is not None
        if not connected:
            hint = ("Compass is not connected to a Google account yet, so it cannot see your "
                    "Drive. Connect the read-only Apps Script bridge in Settings, Connections, "
                    "then come back and re-detect.")
        elif public["status"] == "partial":
            hint = (f"Found the COLLEGE folder but no spreadsheet named "
                    f"\"{settings.college_dashboard_name}\" inside it. If you renamed it, rename "
                    "it back, or run setUp() from college-os/setup.gs to recreate it.")
        else:
            hint = ("Compass could not find a spreadsheet named "
                    f"\"{settings.college_dashboard_name}\" in your Drive. Run setUp() from "
                    "college-os/setup.gs, then re-detect.")
        return {"link": public, "dashboard": None, "importable": [], "imports": [], "hint": hint}

    dashboard = await read_dashboard(profile, force=force)
    available = quest_service.available_evidence_types()
    candidates = importable(dashboard, available)
    imports = await _imports(profile["id"])
    for key, draft in candidates.items():
        record = imports.get(key)
        draft["imported_quest_id"] = record.get("quest_id") if record else None
        draft["quest_state"] = record.get("quest_state") if record else None

    return {
        "link": public,
        "dashboard": dashboard,
        "importable": sorted(candidates.values(), key=lambda d: (d["tab"], d["title"])),
        "imports": [
            {"source_key": k, "tab": v["tab"], "area": v["area"], "title": v["title"],
             "quest_id": v["quest_id"], "quest_state": v.get("quest_state"),
             "imported_at": v["imported_at"]}
            for k, v in sorted(imports.items(), key=lambda kv: kv[1]["imported_at"], reverse=True)
        ],
        "available_evidence_types": available,
        "rhythms": RHYTHM_TITLES,
        "task_lists": TASK_LIST_NAMES,
    }
