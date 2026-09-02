"""A small iCalendar reader, enough for Canvas calendar feeds.

Deliberately dependency-free: RFC 5545 is a line-oriented format and the subset
Canvas emits is narrow, so a parser is cheaper than another pinned package.

Handles the parts that actually bite: CRLF or LF line endings, folded lines
(a continuation begins with a space or tab), property parameters after a
semicolon, escaped commas/semicolons/newlines in TEXT values, and both
date-times (`20260918T235900Z`, floating, or `TZID=`-qualified) and all-day
`VALUE=DATE` values.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

# Canvas uses these UID shapes; the prefix is how an assignment is told from a
# lecture slot or an instructor-authored calendar entry.
_ASSIGNMENT_UID = re.compile(r"assignment[-_]", re.I)

# "Essay 1 [BIOL 240 Fall 2026]" — Canvas appends the course in brackets.
_COURSE_SUFFIX = re.compile(r"\s*\[([^\]]+)\]\s*$")


def _unfold(text: str) -> list[str]:
    """Join folded continuation lines back onto their property line."""
    raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    for line in raw:
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def _unescape(value: str) -> str:
    return (value.replace("\\n", "\n").replace("\\N", "\n")
                 .replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\"))


def _parse_dt(value: str, params: dict[str, str]) -> tuple[datetime | None, bool]:
    """Return (aware datetime, all_day). Floating times are read as UTC."""
    value = value.strip()
    if params.get("VALUE", "").upper() == "DATE" or (len(value) == 8 and "T" not in value):
        try:
            d = datetime.strptime(value, "%Y%m%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None, False
        return d, True
    fmt = "%Y%m%dT%H%M%SZ" if value.endswith("Z") else "%Y%m%dT%H%M%S"
    try:
        dt = datetime.strptime(value, fmt)
    except ValueError:
        return None, False
    # A TZID we cannot resolve without tz data is still better read as UTC than
    # dropped; the date is what a due-date feed is actually for.
    return dt.replace(tzinfo=timezone.utc), False


def parse(text: str) -> list[dict]:
    """Every VEVENT in the feed, as plain dicts."""
    events: list[dict] = []
    current: dict | None = None
    for line in _unfold(text):
        stripped = line.strip()
        if stripped == "BEGIN:VEVENT":
            current = {}
            continue
        if stripped == "END:VEVENT":
            if current is not None:
                events.append(current)
            current = None
            continue
        if current is None or ":" not in line:
            continue
        head, _, value = line.partition(":")
        name, *param_parts = head.split(";")
        params = {}
        for part in param_parts:
            key, _, val = part.partition("=")
            params[key.strip().upper()] = val.strip().strip('"')
        current[name.strip().upper()] = (value, params)
    return events


def assignments(text: str, *, limit: int = 200, canvas_only: bool = True) -> list[dict]:
    """Dated entries from a calendar feed, earliest deadline first.

    With `canvas_only` (the default, for a Canvas feed) only VEVENTs whose UID
    marks them as an assignment are returned: a Canvas feed also carries lecture
    slots and instructor-authored events, which are not work the student owes
    anyone. Other feeds have no such convention — a student who adds one has
    already chosen what it contains — so every dated event counts.
    """
    out: list[dict] = []
    for event in parse(text):
        uid = event.get("UID", ("", {}))[0]
        if canvas_only and not _ASSIGNMENT_UID.search(uid):
            continue
        summary_raw, _ = event.get("SUMMARY", ("", {}))
        summary = _unescape(summary_raw).strip()
        if not summary:
            continue
        start = event.get("DTSTART")
        due, all_day = _parse_dt(*start) if start else (None, False)
        if due is None:
            continue
        course = None
        match = _COURSE_SUFFIX.search(summary)
        if match:
            course = match.group(1).strip()
            summary = _COURSE_SUFFIX.sub("", summary).strip()
        description = _unescape(event.get("DESCRIPTION", ("", {}))[0]).strip()
        out.append({
            "uid": uid,
            "title": summary[:200],
            "course": (course or "")[:120] or None,
            "due_at": due.isoformat(),
            "all_day": all_day,
            "url": event.get("URL", ("", {}))[0].strip() or None,
            # Canvas puts the assignment description here; it is the student's
            # own coursework text, so it stays local like everything else.
            "description": description[:2000] or None,
        })
    out.sort(key=lambda a: a["due_at"])
    return out[:limit]


def upcoming(items: list[dict], *, now: datetime | None = None, days: int = 60) -> list[dict]:
    """Assignments still ahead, within a horizon."""
    now = now or datetime.now(timezone.utc)
    horizon = now + timedelta(days=days)
    ahead = []
    for a in items:
        try:
            due = datetime.fromisoformat(a["due_at"])
        except ValueError:
            continue
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        if now <= due <= horizon:
            ahead.append(a)
    return ahead


__all__ = ["parse", "assignments", "upcoming", "date"]
