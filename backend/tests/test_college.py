"""College OS integration: detection, dashboard parsing, and quest import."""
from app.services import college
from conftest import create_profile, wait_until

DASHBOARD_ID = "sheet-college-dashboard"

THIS_WEEK = [
    ["Area", "Goal", "Definition of Done", "Progress", "Evidence"],
    ["Academics", "Stay ahead", "Everything submitted ≥24h early", "", "Tasks"],
    ["Research", "Start outreach", "3 emails sent", "", "Gmail"],
    ["Projects", "Advance prototype", "Sensor test complete", "", "Drive"],
    [],
    ["THIS WEEK'S BIG 3"],
    ["1. Ship the sensor rig"],
    ["2."],
    ["3. Email Professor Patel"],
    [],
    ["NOT THIS WEEK"],
    ["Redesign the club website"],
]

SEMESTER = [
    ["Area", "Semester outcome", "Metric / how I would know", "Status"],
    ["Research", "Join a research lab", "≥10 targeted outreach emails, lab secured", "In progress"],
    ["Projects", "Ship a usable milestone", "MVP committed to GitHub", ""],
    ["", "", "", ""],
]

OPPORTUNITIES = [
    ["Opportunity", "Type", "Deadline", "Value", "Probability", "Next Action", "Status"],
    ["AI Lab", "Research", "2026-09-15", "High", "Medium", "Email professor", "RESEARCHING"],
    ["Old competition", "Entrepreneurship", "", "Low", "Low", "", "PASSED / REJECTED"],
]

REVIEWS = [
    ["Week of", "Goal", "Result", "Completed?", "Evidence", "Why", "Failure type", "Change next week"],
    ["2026-08-16", "Contact three labs", "2/3", "PARTIAL", "Emails to Smith and Patel", "Polished too long", "PLAN", "Cap drafting"],
    ["2026-08-09", "Finish problem set", "done", "YES", "Submitted Aug 10", "", "", ""],
    ["2026-08-02", "Start prototype", "nothing", "NO", "", "Never scheduled it", "PLAN", "Time-block it"],
]

TIME_LOG = [
    ["Date", "Task", "Category", "Estimated (min)", "Actual (min)", "Ratio"],
    ["2026-08-10", "Problem set", "Problem sets", 60, 120, "2.00"],
    ["2026-08-11", "Problem set", "Problem sets", 30, 60, "2.00"],
    ["2026-08-12", "Problem set", "Problem sets", 40, 60, "1.50"],
    ["2026-08-13", "Write memo", "Writing", 60, 60, "1.00"],
    ["2026-08-14", "Broken row", "Writing", "", "", ""],
]

TABS = {
    "THIS WEEK": THIS_WEEK,
    "SEMESTER GOALS": SEMESTER,
    "OPPORTUNITIES": OPPORTUNITIES,
    "WEEKLY REVIEWS": REVIEWS,
    "TIME LOG": TIME_LOG,
}


def seed_college_workspace(env):
    env.script.files = [
        {"id": DASHBOARD_ID, "name": "COLLEGE DASHBOARD",
         "mime_type": "application/vnd.google-apps.spreadsheet",
         "modified_time": "2026-08-20T10:00:00Z", "created_time": "2026-08-01T10:00:00Z"},
        {"id": "folder-college", "name": "COLLEGE",
         "mime_type": "application/vnd.google-apps.folder",
         "modified_time": "2026-08-01T10:00:00Z"},
        {"id": "doc-ph", "name": "PROJECT HOME — Sensor rig",
         "mime_type": "application/vnd.google-apps.document",
         "modified_time": "2026-08-19T10:00:00Z"},
        {"id": "doc-other", "name": "Unrelated notes",
         "mime_type": "application/vnd.google-apps.document",
         "modified_time": "2026-08-19T10:00:00Z"},
    ]
    env.script.sheets = {DASHBOARD_ID: TABS}
    env.script.calendars = [{"id": "cal-1", "summary": "Academic"},
                           {"id": "cal-2", "summary": "Opportunities"},
                           {"id": "cal-3", "summary": "Random other calendar"}]


# ------------------------------------------------------------------ parsing

def test_parse_this_week_splits_sections():
    parsed = college.parse_this_week([[str(c) for c in row] for row in THIS_WEEK])
    assert [a["area"] for a in parsed["areas"]] == ["Academics", "Research", "Projects"]
    assert parsed["areas"][1]["definition_of_done"] == "3 emails sent"
    # "2." is an empty placeholder and must not become a Big 3 item.
    assert [b["text"] for b in parsed["big_three"]] == ["Ship the sensor rig", "Email Professor Patel"]
    assert parsed["not_this_week"] == ["Redesign the club website"]


def test_parse_weekly_reviews_diagnoses_failures():
    parsed = college.parse_weekly_reviews([[str(c) for c in row] for row in REVIEWS])
    assert parsed["total"] == 3
    assert parsed["outcomes"] == {"YES": 1, "PARTIAL": 1, "NO": 1}
    assert parsed["failure_types"]["PLAN"] == 2
    assert parsed["dominant_failure"] == "PLAN"
    assert parsed["evidence_rate"] == 0.67  # 2 of 3 rows cited evidence


def test_parse_time_log_recomputes_multipliers():
    parsed = college.parse_time_log([[str(c) for c in row] for row in TIME_LOG])
    by_category = {m["category"]: m for m in parsed["multipliers"]}
    assert by_category["Problem sets"]["multiplier"] == 1.83
    assert by_category["Problem sets"]["confident"] is True
    # One sample is not a calibration.
    assert by_category["Writing"]["samples"] == 1
    assert by_category["Writing"]["confident"] is False
    assert parsed["samples"] == 4


def test_evidence_column_maps_to_compass_specs():
    available = ["file_created", "file_modified", "email_sent", "github_commit_created",
                 "manual_confirmation"]
    assert college.evidence_specs_for("Gmail", available) == ["email_sent"]
    assert college.evidence_specs_for("Drive", available) == ["file_created", "file_modified"]
    # Google Tasks is not a Compass connector — say so instead of faking it.
    assert college.evidence_specs_for("Tasks", available) == ["manual_confirmation"]
    assert college.evidence_specs_for("", available) == ["manual_confirmation"]
    # Never proposes an evidence type this connection cannot observe.
    assert college.evidence_specs_for("Meet recording", available) == ["manual_confirmation"]


# ------------------------------------------------------------------ detection

async def test_detect_finds_dashboard_folder_and_calendars(env):
    await create_profile(env.client)
    seed_college_workspace(env)

    resp = await env.client.post("/api/v1/college/detect")
    assert resp.status_code == 200, resp.text
    link = resp.json()["data"]
    assert link["status"] == "linked"
    assert link["dashboard_file_id"] == DASHBOARD_ID
    assert link["root_folder_id"] == "folder-college"
    assert link["project_home_count"] == 1
    present = {c["name"]: c["present"] for c in link["calendars"]}
    assert present["Academic"] is True
    assert present["Personal"] is False


async def test_status_is_not_detected_without_college_os(env):
    await create_profile(env.client)
    env.script.files = [{"id": "f1", "name": "Grocery list",
                        "mime_type": "application/vnd.google-apps.document",
                        "modified_time": "2026-08-19T10:00:00Z"}]
    resp = await env.client.post("/api/v1/college/detect")
    assert resp.json()["data"]["status"] == "not_detected"

    overview = await env.client.get("/api/v1/college")
    body = overview.json()["data"]
    assert body["dashboard"] is None
    assert "COLLEGE DASHBOARD" in body["hint"]

    # Reading the dashboard is a clean 409, not a crash.
    assert (await env.client.get("/api/v1/college/dashboard")).status_code == 409


# --------------------------------------------------------------- the overview

async def test_overview_exposes_importable_rows(env):
    await create_profile(env.client)
    seed_college_workspace(env)
    await env.client.post("/api/v1/college/detect")

    body = (await env.client.get("/api/v1/college")).json()["data"]
    assert body["link"]["status"] == "linked"
    assert body["dashboard"]["missing_tabs"] == []

    titles = {d["title"] for d in body["importable"]}
    assert "Join a research lab" in titles
    assert "Ship the sensor rig" in titles
    assert "Pursue: AI Lab" in titles
    # Closed pipeline rows are history, not work to import.
    assert "Pursue: Old competition" not in titles

    outreach = next(d for d in body["importable"] if d["title"] == "Start outreach")
    assert outreach["evidence_specs"] == ["email_sent"]
    assert outreach["acceptance_criterion"] == "3 emails sent"

    ai_lab = next(d for d in body["importable"] if d["title"] == "Pursue: AI Lab")
    assert ai_lab["target_date"] == "2026-09-15"


async def test_dashboard_content_is_never_persisted(env):
    """Cell content is file content: memory only, never SQLite."""
    from app import db

    await create_profile(env.client)
    seed_college_workspace(env)
    await env.client.post("/api/v1/college/detect")
    await env.client.get("/api/v1/college/dashboard")

    for table in ("tool_cache", "analytics_cache", "llm_cache"):
        cur = await db.get().execute(f"SELECT * FROM {table}")
        blob = " ".join(str(dict(r)) for r in await cur.fetchall())
        assert "Ship the sensor rig" not in blob
        assert "Join a research lab" not in blob


# ------------------------------------------------------------------ importing

async def test_a_range_ignoring_sheet_read_does_not_mis_parse_tabs(env):
    """If every tab read returns the same rows, report missing — never guess."""
    await create_profile(env.client)
    seed_college_workspace(env)

    def ignores_range(fn, args):
        if fn == "sheets.get_values":
            env.script.calls.append((fn, args))
            return {"values": THIS_WEEK}
        return original(fn, args)

    original = env.script.respond
    env.script.respond = ignores_range
    try:
        await env.client.post("/api/v1/college/detect")
        body = (await env.client.get("/api/v1/college")).json()["data"]
    finally:
        env.script.respond = original

    # Only the tab that really matches its header signature is trusted.
    assert set(body["dashboard"]["missing_tabs"]) == {
        "SEMESTER GOALS", "OPPORTUNITIES", "WEEKLY REVIEWS", "TIME LOG"}
    assert all(d["tab"] == "THIS WEEK" for d in body["importable"])


async def test_import_creates_quests_and_is_idempotent(env):
    await create_profile(env.client)
    seed_college_workspace(env)
    await env.client.post("/api/v1/college/detect")

    body = (await env.client.get("/api/v1/college")).json()["data"]
    lab = next(d for d in body["importable"] if d["title"] == "Join a research lab")

    resp = await env.client.post("/api/v1/college/quests:import",
                                 json={"source_keys": [lab["source_key"]]})
    assert resp.status_code == 201, resp.text
    created = resp.json()["data"]["created"]
    assert len(created) == 1
    quest_id = created[0]["quest_id"]

    quest = (await env.client.get(f"/api/v1/quests/{quest_id}")).json()["data"]
    assert quest["goal"] == "Join a research lab"
    # The sheet's metric travels with the quest, for the planner and the UI.
    assert "≥10 targeted outreach emails" in quest["meaning"]
    assert quest["targets"]["college_os"]["tab"] == "SEMESTER GOALS"
    assert quest["targets"]["college_os"]["source_key"] == lab["source_key"]

    # The planner runs as it does for any other quest.
    await wait_until(lambda: _has_subgoals(env, quest_id))

    # Re-importing the same row does not create a second quest.
    again = await env.client.post("/api/v1/college/quests:import",
                                  json={"source_keys": [lab["source_key"]]})
    assert again.json()["data"]["created"] == []
    assert again.json()["data"]["skipped"][0]["quest_id"] == quest_id

    after = (await env.client.get("/api/v1/college")).json()["data"]
    lab_after = next(d for d in after["importable"] if d["title"] == "Join a research lab")
    assert lab_after["imported_quest_id"] == quest_id
    assert len(after["imports"]) == 1


async def _has_subgoals(env, quest_id):
    quest = (await env.client.get(f"/api/v1/quests/{quest_id}")).json()["data"]
    return len(quest["subgoals"]) > 0


async def test_import_rejects_unknown_rows(env):
    await create_profile(env.client)
    seed_college_workspace(env)
    await env.client.post("/api/v1/college/detect")

    resp = await env.client.post("/api/v1/college/quests:import",
                                 json={"source_keys": ["semester_goals:deadbeefdeadbeef"]})
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["created"] == []
    assert data["unknown"] == ["semester_goals:deadbeefdeadbeef"]


async def test_unlink_forgets_everything_local(env):
    await create_profile(env.client)
    seed_college_workspace(env)
    await env.client.post("/api/v1/college/detect")
    body = (await env.client.get("/api/v1/college")).json()["data"]
    key = body["importable"][0]["source_key"]
    await env.client.post("/api/v1/college/quests:import", json={"source_keys": [key]})

    resp = await env.client.request("DELETE", "/api/v1/college/link")
    assert resp.json()["data"]["unlinked"] is True
    assert (await env.client.get("/api/v1/college/status")).json()["data"]["status"] == "not_detected"

    # Compass never writes to Google — unlinking cannot have touched the sheet.
    write_calls = [c for c in env.script.calls
                   if any(v in c[0] for v in ("create", "update", "delete", "insert"))]
    assert write_calls == []


async def test_import_is_present_in_the_privacy_export(env):
    await create_profile(env.client)
    seed_college_workspace(env)
    await env.client.post("/api/v1/college/detect")
    body = (await env.client.get("/api/v1/college")).json()["data"]
    await env.client.post("/api/v1/college/quests:import",
                          json={"source_keys": [body["importable"][0]["source_key"]]})

    export = (await env.client.get("/api/v1/me/export")).json()["data"]
    assert export["college_link"]["dashboard_file_id"] == DASHBOARD_ID
    assert len(export["college_imports"]) == 1


async def test_the_hint_names_the_real_blocker(env, monkeypatch):
    """Telling someone to run a provisioner when Compass cannot see their Drive
    at all sends them to the wrong place."""
    from app import providers as provider_service
    from app.services import college
    from tests.conftest import create_profile

    profile = await create_profile(env.client, "Student")
    pid = profile["profile"]["id"]

    async def unconnected(_profile):
        return None
    monkeypatch.setattr(provider_service, "active_provider", unconnected)
    result = await college.overview({"id": pid, "display_name": "Student"})
    assert "not connected to a Google account" in result["hint"]
    assert "setUp()" not in result["hint"]

    async def connected(_profile):
        return "bridge"
    monkeypatch.setattr(provider_service, "active_provider", connected)
    result = await college.overview({"id": pid, "display_name": "Student"})
    assert "setUp()" in result["hint"]
