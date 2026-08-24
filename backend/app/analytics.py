"""Pure computation over already-fetched Calendar events / Drive files.

No network calls here - these functions take plain lists of dicts (as
returned by services/*.py) and return plain dicts, so they're trivially
unit-testable against fixture JSON.
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def _tz(tz_name: str = "UTC") -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("UTC")


def _parse_event_window(event: dict, tz_name: str = "UTC") -> tuple[datetime, datetime] | None:
    """Return (start, end) in the profile's local timezone, or None for all-day/unparseable events."""
    start = event.get("start") or {}
    end = event.get("end") or {}
    start_dt_raw = start.get("date_time")
    end_dt_raw = end.get("date_time")
    if not start_dt_raw or not end_dt_raw:
        return None
    try:
        start_dt = datetime.fromisoformat(start_dt_raw.replace("Z", "+00:00")).astimezone(_tz(tz_name))
        end_dt = datetime.fromisoformat(end_dt_raw.replace("Z", "+00:00")).astimezone(_tz(tz_name))
    except ValueError:
        return None
    return start_dt, end_dt


def _is_self_attendee(attendee: dict) -> bool:
    return bool(attendee.get("self")) or bool(attendee.get("resource"))


def compute_calendar_load(events: list[dict], tz_name: str = "UTC",
                          work_start: int = 9, work_end: int = 18) -> dict:
    timed = [(e, w) for e in events if (w := _parse_event_window(e, tz_name)) is not None]

    by_day: dict[str, list[tuple[datetime, datetime]]] = defaultdict(list)
    for _event, (start, end) in timed:
        by_day[start.date().isoformat()].append((start, end))

    meetings_per_day = {day: len(windows) for day, windows in by_day.items()}
    hours_per_day = {
        day: round(sum((end - start).total_seconds() for start, end in windows) / 3600, 2)
        for day, windows in by_day.items()
    }

    work_hours_total = 0.0
    after_hours_total = 0.0
    for _event, (start, end) in timed:
        day_work_start = start.replace(hour=work_start, minute=0, second=0, microsecond=0)
        day_work_end = start.replace(hour=work_end, minute=0, second=0, microsecond=0)
        overlap_start = max(start, day_work_start)
        overlap_end = min(end, day_work_end)
        overlap_hours = max((overlap_end - overlap_start).total_seconds(), 0) / 3600
        total_hours = (end - start).total_seconds() / 3600
        work_hours_total += overlap_hours
        after_hours_total += max(total_hours - overlap_hours, 0)

    work_day_span_hours = max(work_end - work_start, 0)
    free_focus_hours_per_day = {
        day: round(max(work_day_span_hours - hours, 0), 2) for day, hours in hours_per_day.items()
    }

    max_streak = 0
    max_streak_day = None
    for day, windows in by_day.items():
        windows_sorted = sorted(windows, key=lambda w: w[0])
        streak = 1
        best = 1
        for i in range(1, len(windows_sorted)):
            gap = (windows_sorted[i][0] - windows_sorted[i - 1][1]).total_seconds() / 60
            streak = streak + 1 if gap <= 5 else 1
            best = max(best, streak)
        if best > max_streak:
            max_streak, max_streak_day = best, day

    busiest_days = sorted(hours_per_day.items(), key=lambda kv: kv[1], reverse=True)[:5]

    return {
        "meetings_per_day": meetings_per_day,
        "meeting_hours_per_day": hours_per_day,
        "free_focus_hours_per_day": free_focus_hours_per_day,
        "total_meeting_hours": round(sum(hours_per_day.values()), 2),
        "work_hours_meeting_hours": round(work_hours_total, 2),
        "after_hours_meeting_hours": round(after_hours_total, 2),
        "longest_back_to_back_streak": {"count": max_streak, "day": max_streak_day},
        "busiest_days": [{"day": d, "hours": h} for d, h in busiest_days],
    }


def compute_document_activity(files: list[dict], recent_days: int = 30, stale_after_days: int = 90,
                              tz_name: str = "UTC") -> dict:
    now = datetime.now(_tz(tz_name))

    def _parse(ts: str | None) -> datetime | None:
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(_tz())
        except ValueError:
            return None

    enriched = []
    for f in files:
        created = _parse(f.get("created_time"))
        modified = _parse(f.get("modified_time"))
        try:
            size = int(f["size"]) if f.get("size") is not None else None
        except (TypeError, ValueError):
            size = None
        enriched.append({**f, "_created": created, "_modified": modified, "_size": size})

    recent_cutoff = now - timedelta(days=recent_days)
    recently_active = [
        f for f in enriched if f["_modified"] and f["_modified"] >= recent_cutoff
    ]
    recently_active.sort(key=lambda f: f["_modified"], reverse=True)

    stale_cutoff = now - timedelta(days=stale_after_days)
    stale = [f for f in enriched if f["_modified"] and f["_modified"] < stale_cutoff]

    most_active = sorted(
        (f for f in enriched if f["_modified"]), key=lambda f: f["_modified"], reverse=True
    )[:10]

    size_known = all(f["_size"] is not None for f in enriched) if enriched else False
    growth_by_week: dict[str, int] = defaultdict(int)
    for f in enriched:
        if not f["_created"]:
            continue
        year, week, _ = f["_created"].isocalendar()
        key = f"{year}-W{week:02d}"
        growth_by_week[key] += f["_size"] if (size_known and f["_size"]) else 1

    def _slim(f: dict) -> dict:
        return {
            "id": f.get("id"),
            "name": f.get("name"),
            "modified_time": f.get("modified_time"),
            "created_time": f.get("created_time"),
        }

    return {
        "recently_active": [_slim(f) for f in recently_active],
        "most_active_documents": [_slim(f) for f in most_active],
        "stale_documents": [_slim(f) for f in stale],
        "storage_growth_by_week": dict(sorted(growth_by_week.items())),
        "storage_growth_unit": "bytes" if size_known else "file_count",
        "total_documents": len(enriched),
    }


def compute_collaboration_patterns(events: list[dict], files: list[dict], tz_name: str = "UTC") -> dict:
    collaborator_counts: Counter[str] = Counter()
    solo_count = 0
    group_count = 0

    for event in events:
        attendees = [a for a in (event.get("attendees") or []) if not _is_self_attendee(a)]
        if attendees:
            group_count += 1
        else:
            solo_count += 1
        for attendee in attendees:
            email = attendee.get("email")
            if email:
                collaborator_counts[email] += 1

    shared_docs = [
        {"id": f.get("id"), "name": f.get("name")} for f in files if f.get("shared")
    ]

    return {
        "top_collaborators": [
            {"email": email, "meetings": count}
            for email, count in collaborator_counts.most_common(10)
        ],
        "solo_meetings": solo_count,
        "group_meetings": group_count,
        "shared_documents": shared_docs,
        "shared_document_count": len(shared_docs),
    }


def _week_key(dt: datetime) -> str:
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def compute_time_trends(events: list[dict], files: list[dict], tz_name: str = "UTC") -> dict:
    meeting_hours_by_week: dict[str, float] = defaultdict(float)
    meeting_count_by_week: dict[str, int] = defaultdict(int)
    for event in events:
        window = _parse_event_window(event, tz_name)
        if not window:
            continue
        start, end = window
        key = _week_key(start)
        meeting_hours_by_week[key] += (end - start).total_seconds() / 3600
        meeting_count_by_week[key] += 1

    doc_edits_by_week: dict[str, int] = defaultdict(int)
    for f in files:
        ts = f.get("modified_time")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(_tz(tz_name))
        except ValueError:
            continue
        doc_edits_by_week[_week_key(dt)] += 1

    weeks = sorted(set(meeting_hours_by_week) | set(doc_edits_by_week))

    def _wow_delta(series: dict[str, float], week: str, prev_week: str | None) -> float | None:
        if prev_week is None:
            return None
        prev = series.get(prev_week, 0)
        curr = series.get(week, 0)
        if prev == 0:
            return None
        return round((curr - prev) / prev * 100, 1)

    series = []
    for i, week in enumerate(weeks):
        prev_week = weeks[i - 1] if i > 0 else None
        series.append(
            {
                "week": week,
                "meeting_hours": round(meeting_hours_by_week.get(week, 0), 2),
                "meeting_count": meeting_count_by_week.get(week, 0),
                "doc_edits": doc_edits_by_week.get(week, 0),
                "meeting_hours_wow_pct": _wow_delta(meeting_hours_by_week, week, prev_week),
                "doc_edits_wow_pct": _wow_delta(doc_edits_by_week, week, prev_week),
            }
        )

    return {"weeks": series}


def compute_email_activity(snapshot: dict) -> dict:
    """Pure reshape/rank over gmail_service.get_email_snapshot()'s raw bundle
    (weekly volume already comes pre-bucketed from the service, since Gmail's
    list API can't be bucketed client-side - see gmail_service docstring)."""
    sender_counts: Counter[str] = Counter()
    for msg in snapshot.get("recent_messages") or []:
        sender = msg.get("from")
        if sender:
            sender_counts[sender] += 1

    return {
        "messages_per_week": dict(sorted((snapshot.get("volume_by_week") or {}).items())),
        "unread_count": snapshot.get("unread_count", 0),
        "top_senders": [{"sender": s, "count": c} for s, c in sender_counts.most_common(10)],
        "recent_messages": (snapshot.get("recent_messages") or [])[:10],
    }


def compute_meet_activity(records: list[dict], tz_name: str = "UTC") -> dict:
    def _parse(ts: str | None) -> datetime | None:
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(_tz(tz_name))
        except ValueError:
            return None

    timed = []
    for r in records:
        start, end = _parse(r.get("start_time")), _parse(r.get("end_time"))
        if start and end:
            timed.append((start, end))

    meetings_per_week: dict[str, int] = defaultdict(int)
    hours_per_week: dict[str, float] = defaultdict(float)
    durations_minutes = []
    for start, end in timed:
        minutes = (end - start).total_seconds() / 60
        durations_minutes.append(minutes)
        key = _week_key(start)
        meetings_per_week[key] += 1
        hours_per_week[key] += minutes / 60

    return {
        "meetings_per_week": dict(sorted(meetings_per_week.items())),
        "meeting_hours_per_week": {k: round(v, 2) for k, v in sorted(hours_per_week.items())},
        "total_meetings": len(timed),
        "total_meeting_hours": round(sum(durations_minutes) / 60, 2),
        "average_meeting_minutes": round(sum(durations_minutes) / len(durations_minutes), 1) if durations_minutes else 0,
        "longest_meeting_minutes": round(max(durations_minutes), 1) if durations_minutes else 0,
    }


def compute_github_activity(commits: list[dict], pull_requests: list[dict], tz_name: str = "UTC") -> dict:
    def _parse(ts: str | None) -> datetime | None:
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(_tz(tz_name))
        except ValueError:
            return None

    commits_per_week: dict[str, int] = defaultdict(int)
    repo_commit_counts: Counter[str] = Counter()
    for c in commits:
        if c.get("repo"):
            repo_commit_counts[c["repo"]] += 1
        dt = _parse(c.get("created_at"))
        if dt:
            commits_per_week[_week_key(dt)] += 1

    prs_opened_per_week: dict[str, int] = defaultdict(int)
    prs_merged_per_week: dict[str, int] = defaultdict(int)
    open_pr_count = 0
    for pr in pull_requests:
        opened = _parse(pr.get("created_at"))
        if opened:
            prs_opened_per_week[_week_key(opened)] += 1
        merged = _parse(pr.get("merged_at")) if pr.get("merged") else None
        if merged:
            prs_merged_per_week[_week_key(merged)] += 1
        if pr.get("state") == "open":
            open_pr_count += 1

    return {
        "commits_per_week": dict(sorted(commits_per_week.items())),
        "prs_opened_per_week": dict(sorted(prs_opened_per_week.items())),
        "prs_merged_per_week": dict(sorted(prs_merged_per_week.items())),
        "total_commits": len(commits),
        "open_pr_count": open_pr_count,
        "top_repos_by_commits": [{"repo": r, "commits": n} for r, n in repo_commit_counts.most_common(5)],
    }
