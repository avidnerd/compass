"""User-scoped Insights: the ported analytics plus Compass-native metrics.

Analytics cache keys embed the dependent connector generations, so a
connector refresh naturally rolls the keys instead of broad invalidation.
When the provider is down, raw fetches serve stale rows with a visible flag.
"""
import json
import logging
from datetime import timedelta

from .. import analytics, cache, db, telemetry
from ..config import settings
from ..util import now, now_iso, parse_iso

logger = logging.getLogger("compass.insights")


async def _gens(profile_id: str, connectors: list[str]) -> dict:
    return {c: await cache.connector_generation(profile_id, c) for c in connectors}


async def _workspace_files(profile: dict, refresh: bool) -> tuple[list[dict], dict]:
    files, meta = await telemetry.list_drive_files(profile, force=refresh, serve_stale_on_error=True)
    docs = [f for f in files if f.get("mime_type") in telemetry.WORKSPACE_MIMES]
    return docs, meta


async def _events(profile: dict, weeks: int, refresh: bool) -> tuple[list[dict], dict]:
    return await telemetry.calendar_activity(
        profile, now() - timedelta(weeks=weeks), now() + timedelta(days=7),
        force=refresh, serve_stale_on_error=True)


async def _email_snapshot(profile: dict, weeks: int, refresh: bool) -> tuple[dict, dict]:
    """Ported Gmail weekly-volume snapshot (bounded, cached)."""
    from ..capabilities import current_registry
    reg = current_registry()
    arguments = {"weeks_back": weeks, "recent_limit": 10}

    async def fetch() -> dict:
        from .. import providers
        get_tool = reg.resolve("gmail.get_message")
        monday = now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now().weekday())
        volume = {}
        for i in range(weeks - 1, -1, -1):
            ws = monday - timedelta(weeks=i)
            we = ws + timedelta(days=7)
            q = f"after:{ws.strftime('%Y/%m/%d')} before:{we.strftime('%Y/%m/%d')}"
            payload = await providers.call(profile, "gmail.list_messages", {"q": q, "maxResults": 1})
            volume[ws.strftime("%Y-%m-%d")] = payload.get("result_size_estimate") or 0
        unread = (await providers.call(profile, "gmail.list_messages",
                                       {"q": "is:unread", "maxResults": 1})
                  ).get("result_size_estimate") or 0
        refs = (await providers.call(profile, "gmail.list_messages",
                                     {"maxResults": 10})).get("messages") or []
        recent = []
        if get_tool:
            for ref in refs:
                detail = await providers.call(profile, "gmail.get_message", {"message_id": ref["id"]})
                headers = (detail.get("payload") or {}).get("headers") or []

                def header(name: str):
                    for h in headers:
                        if (h.get("name") or "").lower() == name.lower():
                            return h.get("value")
                    return None
                recent.append({"id": detail.get("id"), "from": header("From"),
                               "subject": header("Subject"), "date": header("Date"),
                               "snippet": detail.get("snippet")})
        return {"volume_by_week": volume, "unread_count": unread, "recent_messages": recent}

    if reg is None or reg.resolve("gmail.list_messages") is None:
        return {"volume_by_week": {}, "unread_count": 0, "recent_messages": []}, {"from_cache": False, "stale": False, "unavailable": True}
    return await cache.get_or_fetch(
        scope_id=profile["id"], connector="gmail", capability="gmail.activity_snapshot",
        arguments=arguments, ttl_seconds=settings.ttl_gmail_activity, fetch_fn=fetch,
        force=refresh, serve_stale_on_error=True)


async def _rollup(profile: dict, metric: str, params: dict, connectors: list[str],
                  compute_fn, refresh: bool) -> tuple[dict, dict]:
    gens = await _gens(profile["id"], connectors)
    return await cache.get_or_compute(
        profile["id"], metric, {**params, "gens": gens}, settings.ttl_analytics,
        compute_fn, force=refresh)


async def calendar_load(profile: dict, weeks: int = 8, refresh: bool = False):
    events, meta = await _events(profile, weeks, refresh)
    result, m2 = await _rollup(
        profile, "calendar_load", {"weeks": weeks}, ["google_calendar"],
        lambda: analytics.compute_calendar_load(events, profile["timezone"],
                                                profile["work_hours_start"], profile["work_hours_end"]),
        refresh)
    return result, [meta, m2]


async def document_activity(profile: dict, refresh: bool = False):
    files, meta = await _workspace_files(profile, refresh)
    result, m2 = await _rollup(
        profile, "document_activity", {"recent_days": 30}, ["google_drive"],
        lambda: analytics.compute_document_activity(files, tz_name=profile["timezone"]), refresh)
    return result, [meta, m2]


async def collaboration(profile: dict, weeks: int = 8, refresh: bool = False):
    events, m1 = await _events(profile, weeks, refresh)
    files, m2 = await _workspace_files(profile, refresh)
    result, m3 = await _rollup(
        profile, "collaboration_patterns", {"weeks": weeks}, ["google_calendar", "google_drive"],
        lambda: analytics.compute_collaboration_patterns(events, files, profile["timezone"]), refresh)
    return result, [m1, m2, m3]


async def trends(profile: dict, weeks: int = 8, refresh: bool = False):
    events, m1 = await _events(profile, weeks, refresh)
    files, m2 = await _workspace_files(profile, refresh)
    result, m3 = await _rollup(
        profile, "time_trends", {"weeks": weeks}, ["google_calendar", "google_drive"],
        lambda: analytics.compute_time_trends(events, files, profile["timezone"]), refresh)
    return result, [m1, m2, m3]


async def email_activity(profile: dict, weeks: int = 8, refresh: bool = False):
    snapshot, m1 = await _email_snapshot(profile, weeks, refresh)
    result, m2 = await _rollup(
        profile, "email_activity", {"weeks": weeks}, ["gmail"],
        lambda: analytics.compute_email_activity(snapshot), refresh)
    return result, [m1, m2]


async def meet_activity(profile: dict, weeks: int = 8, refresh: bool = False):
    records, m1 = await telemetry.meet_activity(
        profile, now() - timedelta(weeks=weeks), force=refresh, serve_stale_on_error=True)
    result, m2 = await _rollup(
        profile, "meet_activity", {"weeks": weeks}, ["google_meet"],
        lambda: analytics.compute_meet_activity(records, profile["timezone"]), refresh)
    return result, [m1, m2]


async def github_activity(profile: dict, weeks: int = 8, refresh: bool = False):
    raw, m1 = await telemetry.github_activity(
        profile, now() - timedelta(weeks=weeks), force=refresh, serve_stale_on_error=True)
    result, m2 = await _rollup(
        profile, "github_activity", {"weeks": weeks}, ["github"],
        lambda: analytics.compute_github_activity(raw.get("commits") or [],
                                                  raw.get("pull_requests") or [],
                                                  profile["timezone"]), refresh)
    return result, [m1, m2]


async def summary(profile: dict, weeks: int = 8, refresh: bool = False):
    data: dict = {}
    metas: list[dict] = []
    for key, fn in (("calendar_load", calendar_load), ("collaboration", collaboration),
                    ("trends", trends)):
        try:
            result, ms = await fn(profile, weeks=weeks, refresh=refresh)
            data[key] = result
            metas.extend(ms)
        except Exception as exc:
            data[key] = None
            data[f"{key}_error"] = getattr(exc, "code", type(exc).__name__)
    for key, fn in (("document_activity", document_activity),):
        try:
            result, ms = await fn(profile, refresh=refresh)
            data[key] = result
            metas.extend(ms)
        except Exception as exc:
            data[key] = None
            data[f"{key}_error"] = getattr(exc, "code", type(exc).__name__)
    for key, fn in (("email_activity", email_activity), ("meet_activity", meet_activity),
                    ("github_activity", github_activity)):
        try:
            result, ms = await fn(profile, weeks=weeks, refresh=refresh)
            data[key] = result
            metas.extend(ms)
        except Exception as exc:
            data[key] = None
            data[f"{key}_error"] = getattr(exc, "code", type(exc).__name__)
    data["baseline"] = await baseline(profile["id"])
    return data, metas


# ------------------------------------------------------ Compass-native

async def baseline(profile_id: str) -> dict:
    """Personal baseline: the user compared to their own recent sessions."""
    cur = await db.get().execute(
        """SELECT focus_score, planned_seconds, paused_total_seconds, started_at, finished_at
           FROM focus_sessions WHERE profile_id = ? AND state = 'completed' AND focus_score IS NOT NULL
           ORDER BY created_at DESC LIMIT 14""", (profile_id,))
    rows = [dict(r) for r in await cur.fetchall()]
    scores = [r["focus_score"] for r in rows]
    return {
        "eligible_sessions": len(scores),
        "average_focus_score": round(sum(scores) / len(scores), 1) if scores else None,
        "best_focus_score": max(scores) if scores else None,
        "recent_scores": scores,
        "baseline_ready": len(scores) >= 5,
    }


async def session_history(profile_id: str, limit: int = 50) -> list[dict]:
    cur = await db.get().execute(
        """SELECT s.id, s.state, s.planned_seconds, s.paused_total_seconds, s.started_at,
                  s.finished_at, s.focus_score, s.demo, q.category,
                  v.result AS verification_result, v.human_confirmed
           FROM focus_sessions s
           LEFT JOIN quests q ON q.id = s.quest_id
           LEFT JOIN verifications v ON v.session_id = s.id
           WHERE s.profile_id = ? ORDER BY s.created_at DESC LIMIT ?""",
        (profile_id, min(limit, 100)))
    return [dict(r) for r in await cur.fetchall()]


async def stat_growth(profile_id: str, limit: int = 100) -> list[dict]:
    cur = await db.get().execute(
        "SELECT xp, care_points, stats_json, reason, created_at FROM stat_ledger"
        " WHERE profile_id = ? ORDER BY created_at DESC LIMIT ?", (profile_id, min(limit, 200)))
    return [{**dict(r), "stats": json.loads(r["stats_json"])} for r in await cur.fetchall()]


async def verification_history(profile_id: str, limit: int = 50) -> list[dict]:
    cur = await db.get().execute(
        """SELECT v.id, v.session_id, v.result, v.confidence, v.explanation, v.model_id,
                  v.human_confirmed, v.created_at, s.title AS subgoal_title
           FROM verifications v LEFT JOIN subgoals s ON s.id = v.subgoal_id
           WHERE v.profile_id = ? ORDER BY v.created_at DESC LIMIT ?""",
        (profile_id, min(limit, 100)))
    return [dict(r) for r in await cur.fetchall()]


async def freshness(profile_id: str) -> list[dict]:
    cur = await db.get().execute(
        """SELECT connector, MAX(fetched_at) AS last_fetched_at, MIN(expires_at) AS next_expiry,
                  COUNT(*) AS cached_rows
           FROM tool_cache WHERE scope_id = ? GROUP BY connector""", (profile_id,))
    rows = {r["connector"]: dict(r) for r in await cur.fetchall()}
    cur = await db.get().execute(
        "SELECT connector, status, generation, last_checked_at FROM connector_states WHERE profile_id = ?",
        (profile_id,))
    out = []
    for r in await cur.fetchall():
        entry = {"connector": r["connector"], "status": r["status"], "generation": r["generation"],
                 "last_checked_at": r["last_checked_at"], "last_fetched_at": None,
                 "cached_rows": 0, "next_expiry": None}
        if r["connector"] in rows:
            entry.update({k: rows[r["connector"]][k] for k in ("last_fetched_at", "cached_rows", "next_expiry")})
        out.append(entry)
    return out
