import json
from pathlib import Path

from app.analytics import (
    _week_key,
    compute_calendar_load,
    compute_collaboration_patterns,
    compute_document_activity,
    compute_email_activity,
    compute_github_activity,
    compute_meet_activity,
    compute_time_trends,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load_events():
    return json.loads((FIXTURES / "events_sample.json").read_text())


def load_files():
    return json.loads((FIXTURES / "files_sample.json").read_text())


def test_compute_calendar_load():
    result = compute_calendar_load(load_events())

    # evt_5 is all-day (no date_time) and must be excluded from every timed metric
    assert result["meetings_per_day"] == {"2026-03-02": 3, "2026-03-09": 1}
    assert result["meeting_hours_per_day"] == {"2026-03-02": 2.0, "2026-03-09": 1.0}
    assert result["total_meeting_hours"] == 3.0
    assert result["work_hours_meeting_hours"] == 2.0
    assert result["after_hours_meeting_hours"] == 1.0
    assert result["free_focus_hours_per_day"] == {"2026-03-02": 7.0, "2026-03-09": 8.0}
    # evt_1 (9:00-9:30) and evt_2 (9:30-10:00) are back-to-back (0 min gap); evt_3 is 12h later
    assert result["longest_back_to_back_streak"] == {"count": 2, "day": "2026-03-02"}
    assert result["busiest_days"][0] == {"day": "2026-03-02", "hours": 2.0}


def test_compute_collaboration_patterns():
    result = compute_collaboration_patterns(load_events(), load_files())

    # evt_3 (solo) and evt_5 (all-day, self-only) are solo; evt_1/evt_2/evt_4 have other attendees
    assert result["solo_meetings"] == 2
    assert result["group_meetings"] == 3
    collaborators = {c["email"]: c["meetings"] for c in result["top_collaborators"]}
    assert collaborators == {"manager@example.com": 2, "teammate1@example.com": 1, "teammate2@example.com": 1}
    assert result["shared_document_count"] == 1
    assert result["shared_documents"] == [{"id": "file_2", "name": "Shared Roadmap"}]


def test_compute_document_activity_stale_and_growth():
    # Use dynamically-generated relative timestamps for the recency/staleness
    # boundaries specifically, since those depend on datetime.now() at test
    # run time and can't be baked into a static fixture.
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    files = [
        {
            "id": "recent",
            "name": "Recent Doc",
            "mime_type": "application/vnd.google-apps.document",
            "created_time": (now - timedelta(days=5)).isoformat().replace("+00:00", "Z"),
            "modified_time": (now - timedelta(days=1)).isoformat().replace("+00:00", "Z"),
            "shared": False,
            "size": "100",
        },
        {
            "id": "stale",
            "name": "Stale Doc",
            "mime_type": "application/vnd.google-apps.document",
            "created_time": (now - timedelta(days=400)).isoformat().replace("+00:00", "Z"),
            "modified_time": (now - timedelta(days=200)).isoformat().replace("+00:00", "Z"),
            "shared": False,
            "size": "200",
        },
    ]
    result = compute_document_activity(files, recent_days=30, stale_after_days=90)

    assert [f["id"] for f in result["recently_active"]] == ["recent"]
    assert [f["id"] for f in result["stale_documents"]] == ["stale"]
    assert result["storage_growth_unit"] == "bytes"
    assert result["total_documents"] == 2


def test_compute_document_activity_missing_size_falls_back_to_file_count():
    files = [{"id": "f1", "name": "No size", "created_time": "2026-01-01T00:00:00Z", "modified_time": None, "size": None}]
    result = compute_document_activity(files)
    assert result["storage_growth_unit"] == "file_count"


def test_compute_time_trends_week_bucketing_and_wow_deltas():
    events = load_events()
    files = load_files()
    result = compute_time_trends(events, files)
    weeks = {w["week"]: w for w in result["weeks"]}

    from datetime import datetime

    week_evt1 = _week_key(datetime.fromisoformat("2026-03-02T00:00:00+00:00"))
    week_evt4 = _week_key(datetime.fromisoformat("2026-03-09T00:00:00+00:00"))

    assert weeks[week_evt1]["meeting_hours"] == 2.0
    assert weeks[week_evt1]["meeting_count"] == 3
    assert weeks[week_evt4]["meeting_hours"] == 1.0
    assert weeks[week_evt4]["meeting_count"] == 1

    # first chronological week has no prior week to compare against
    first_week = result["weeks"][0]
    assert first_week["meeting_hours_wow_pct"] is None


def test_compute_email_activity():
    snapshot = {
        "volume_by_week": {"2026-03-09": 5, "2026-03-02": 3},
        "unread_count": 4,
        "recent_messages": [
            {"id": "m1", "from": "boss@example.com", "subject": "Q1 plan", "date": "...", "snippet": "..."},
            {"id": "m2", "from": "boss@example.com", "subject": "Re: Q1 plan", "date": "...", "snippet": "..."},
            {"id": "m3", "from": "teammate@example.com", "subject": "Standup notes", "date": "...", "snippet": "..."},
        ],
    }
    result = compute_email_activity(snapshot)

    # weeks come back sorted regardless of input order
    assert list(result["messages_per_week"].keys()) == ["2026-03-02", "2026-03-09"]
    assert result["unread_count"] == 4
    assert result["top_senders"][0] == {"sender": "boss@example.com", "count": 2}
    assert len(result["recent_messages"]) == 3


def test_compute_meet_activity():
    records = [
        {"start_time": "2026-03-02T09:00:00Z", "end_time": "2026-03-02T09:30:00Z"},
        {"start_time": "2026-03-02T10:00:00Z", "end_time": "2026-03-02T11:00:00Z"},
        # missing end_time must be excluded, not crash
        {"start_time": "2026-03-09T09:00:00Z", "end_time": None},
    ]
    result = compute_meet_activity(records)

    assert result["total_meetings"] == 2
    assert result["total_meeting_hours"] == 1.5
    assert result["longest_meeting_minutes"] == 60.0
    assert result["average_meeting_minutes"] == 45.0


def test_compute_github_activity():
    commits = [
        {"created_at": "2026-03-02T12:00:00Z", "repo": "acme/api"},
        {"created_at": "2026-03-02T13:00:00Z", "repo": "acme/api"},
        {"created_at": "2026-03-09T12:00:00Z", "repo": "acme/web"},
    ]
    pull_requests = [
        {"created_at": "2026-03-02T00:00:00Z", "merged": True, "merged_at": "2026-03-03T00:00:00Z", "state": "closed"},
        {"created_at": "2026-03-09T00:00:00Z", "merged": False, "merged_at": None, "state": "open"},
    ]
    result = compute_github_activity(commits, pull_requests)

    from datetime import datetime

    week_1 = _week_key(datetime.fromisoformat("2026-03-02T00:00:00+00:00"))
    week_2 = _week_key(datetime.fromisoformat("2026-03-09T00:00:00+00:00"))

    assert result["total_commits"] == 3
    assert result["commits_per_week"][week_1] == 2
    assert result["commits_per_week"][week_2] == 1
    assert result["prs_opened_per_week"][week_1] == 1
    assert result["prs_merged_per_week"][week_1] == 1
    assert result["open_pr_count"] == 1
    assert result["top_repos_by_commits"][0] == {"repo": "acme/api", "commits": 2}
