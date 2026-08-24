"""Shared API plumbing: envelopes, auth dependency, idempotency."""
import json
import uuid

from fastapi import Depends, Request, Response

from . import db
from .errors import ApiError
from .services import profiles as profile_service
from .util import now_iso

COOKIE_NAME = "compass_session"


def request_id(request: Request) -> str:
    rid = getattr(request.state, "request_id", None)
    if not rid:
        rid = uuid.uuid4().hex[:12]
        request.state.request_id = rid
    return rid


def envelope(data, request: Request, *metas: dict) -> dict:
    """Success envelope: data + request/cache metadata."""
    metas = tuple(m for m in metas if m)
    from_cache = all(m.get("from_cache", False) for m in metas) if metas else None
    stale = any(m.get("stale", False) for m in metas) if metas else None
    expiries = [m["expires_at"] for m in metas if m.get("expires_at")]
    meta = {"request_id": request_id(request), "generated_at": now_iso()}
    if from_cache is not None:
        meta["from_cache"] = from_cache
        meta["stale"] = stale
        if expiries:
            meta["cache_expires_at"] = min(expiries)
    return {"data": data, "meta": meta}


async def current_profile(request: Request) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise ApiError(401, "unauthenticated", "No session. Create a profile or recover one.")
    profile = await profile_service.profile_for_token(token)
    if profile is None:
        raise ApiError(401, "session_expired", "Your session has expired. Recover with your code.")
    return profile


CurrentProfile = Depends(current_profile)


def set_session_cookie(response: Response, token: str, secure: bool = False) -> None:
    response.set_cookie(
        COOKIE_NAME, token, httponly=True, samesite="lax", secure=secure,
        max_age=30 * 24 * 3600, path="/")


async def idempotent(request: Request, profile_id: str, endpoint: str, handler):
    """Replay-safe mutation: same Idempotency-Key returns the stored response."""
    key = request.headers.get("Idempotency-Key")
    if not key:
        return await handler()
    conn = db.get()
    cur = await conn.execute(
        "SELECT response_json FROM idempotency_records WHERE profile_id = ? AND endpoint = ? AND idem_key = ?",
        (profile_id, endpoint, key))
    row = await cur.fetchone()
    if row is not None:
        return json.loads(row["response_json"])
    result = await handler()
    try:
        await conn.execute(
            "INSERT INTO idempotency_records (profile_id, idem_key, endpoint, response_json, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (profile_id, key, endpoint, json.dumps(result, default=str), now_iso()))
        await conn.commit()
    except Exception:
        await conn.rollback()
    return result


def check_if_match(request: Request, current_version: int) -> None:
    """Lightweight optimistic concurrency: If-Match holds the resource version."""
    if_match = request.headers.get("If-Match")
    if if_match is not None and if_match.strip('"') != str(current_version):
        raise ApiError(412, "version_conflict",
                       "The resource changed since you loaded it. Refresh and retry.")
