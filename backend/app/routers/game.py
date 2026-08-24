"""Character, quests, focus sessions, verifications."""
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from ..api import CurrentProfile, check_if_match, envelope, idempotent
from ..errors import ApiError, not_found
from ..services import character as character_service
from ..services import focus as focus_service
from .. import focus_monitoring
from ..services import quests as quest_service

router = APIRouter()


# ------------------------------------------------------------- character

@router.get("/character")
async def get_character(request: Request, profile: dict = CurrentProfile):
    ch = await character_service.get_character(profile["id"])
    return envelope(character_service.public_character(ch), request)


@router.post("/character", status_code=201)
async def create_character(request: Request, profile: dict = CurrentProfile):
    body = await request.json()
    ch = await character_service.finalize_companion(profile["id"], body or {})
    return envelope(character_service.public_character(ch), request)


@router.patch("/character")
async def patch_character(request: Request, profile: dict = CurrentProfile):
    body = await request.json()
    current = await character_service.get_character(profile["id"], apply_drift=False)
    check_if_match(request, current["version"])
    ch = await character_service.update_character(profile["id"], body or {})
    return envelope(character_service.public_character(ch), request)


class CareActionBody(BaseModel):
    action: str
    note: str | None = Field(default=None, max_length=300)
    cosmetic: str | None = Field(default=None, max_length=60)


@router.post("/character/actions")
async def care_action(body: CareActionBody, request: Request, profile: dict = CurrentProfile):
    result = await character_service.care_action(profile["id"], body.action, body.note, body.cosmetic)
    return envelope(result, request)


@router.get("/character/memories")
async def memories(request: Request, cursor: str | None = None, limit: int = 50,
                   profile: dict = CurrentProfile):
    items = await character_service.list_memories(profile["id"], limit=limit, cursor=cursor)
    next_cursor = items[-1]["created_at"] if len(items) == min(limit, 100) else None
    return envelope({"items": items, "next_cursor": next_cursor}, request)


@router.patch("/character/memories/{memory_id}")
async def edit_memory(memory_id: str, request: Request, profile: dict = CurrentProfile):
    body = await request.json()
    text = (body or {}).get("text", "").strip()
    if not text:
        raise ApiError(422, "invalid_request", "Memory text cannot be empty.")
    from .. import db
    from ..util import now_iso
    cur = await db.get().execute("SELECT profile_id FROM character_memories WHERE id = ?", (memory_id,))
    row = await cur.fetchone()
    if row is None:
        raise not_found("memory")
    if row["profile_id"] != profile["id"]:
        raise ApiError(403, "forbidden", "Not your memory.")
    await db.get().execute("UPDATE character_memories SET text = ?, updated_at = ? WHERE id = ?",
                           (text[:300], now_iso(), memory_id))
    await db.get().commit()
    return envelope({"id": memory_id, "text": text[:300]}, request)


@router.delete("/character/memories/{memory_id}")
async def delete_memory(memory_id: str, request: Request, profile: dict = CurrentProfile):
    from .. import db
    cur = await db.get().execute("SELECT profile_id FROM character_memories WHERE id = ?", (memory_id,))
    row = await cur.fetchone()
    if row is None:
        raise not_found("memory")
    if row["profile_id"] != profile["id"]:
        raise ApiError(403, "forbidden", "Not your memory.")
    await db.get().execute("DELETE FROM character_memories WHERE id = ?", (memory_id,))
    await db.get().commit()
    return envelope({"deleted": True}, request)


@router.get("/character/unlocks")
async def unlocks(request: Request, profile: dict = CurrentProfile):
    return envelope(await character_service.unlocks(profile["id"]), request)


# ----------------------------------------------------------------- quests

@router.get("/quests")
async def list_quests(request: Request, cursor: str | None = None, limit: int = 50,
                      profile: dict = CurrentProfile):
    items = await quest_service.list_quests(profile["id"], limit=limit, cursor=cursor)
    next_cursor = items[-1]["created_at"] if len(items) == min(limit, 100) else None
    return envelope({"items": items, "next_cursor": next_cursor,
                     "available_evidence_types": quest_service.available_evidence_types()}, request)


@router.post("/quests", status_code=201)
async def create_quest(request: Request, profile: dict = CurrentProfile):
    body = await request.json()

    async def handler():
        return await quest_service.create_quest(profile["id"], body or {})
    quest = await idempotent(request, profile["id"], "POST /quests", handler)
    return envelope(quest, request)


@router.get("/quests/{quest_id}")
async def get_quest(quest_id: str, request: Request, profile: dict = CurrentProfile):
    return envelope(await quest_service.quest_with_subgoals(profile["id"], quest_id), request)


@router.patch("/quests/{quest_id}")
async def patch_quest(quest_id: str, request: Request, profile: dict = CurrentProfile):
    body = await request.json()
    current = await quest_service.quest_row(profile["id"], quest_id)
    check_if_match(request, current["version"])
    return envelope(await quest_service.patch_quest(profile["id"], quest_id, body or {}), request)


@router.post("/quests/{quest_id}:activate")
async def activate_quest(quest_id: str, request: Request, profile: dict = CurrentProfile):
    return envelope(await quest_service.activate_quest(profile["id"], quest_id), request)


@router.post("/quests/{quest_id}:archive")
async def archive_quest(quest_id: str, request: Request, profile: dict = CurrentProfile):
    return envelope(await quest_service.archive_quest(profile["id"], quest_id), request)


# ---------------------------------------------------------- focus sessions

@router.get("/focus-sessions")
async def list_sessions(request: Request, cursor: str | None = None, limit: int = 50,
                        profile: dict = CurrentProfile):
    items = await focus_service.list_sessions(profile["id"], limit=limit, cursor=cursor)
    next_cursor = items[-1]["created_at"] if len(items) == min(limit, 100) else None
    return envelope({"items": items, "next_cursor": next_cursor}, request)


@router.post("/focus-sessions", status_code=201)
async def start_session(request: Request, profile: dict = CurrentProfile):
    body = await request.json()

    async def handler():
        session = await focus_service.start_focus_session(profile, body or {})
        return focus_service.public_session(session)
    return envelope(await idempotent(request, profile["id"], "POST /focus-sessions", handler), request)


@router.get("/focus-sessions/{session_id}")
async def get_session(session_id: str, request: Request, profile: dict = CurrentProfile):
    s = await focus_service.session_row(profile["id"], session_id)
    verification = await focus_service.verification_for_session(profile["id"], session_id)
    return envelope({"session": focus_service.public_session(s), "verification": verification}, request)


@router.post("/focus-sessions/{session_id}:pause")
async def pause_session(session_id: str, request: Request, profile: dict = CurrentProfile):
    s = await focus_service.pause_focus_session(profile["id"], session_id)
    return envelope(focus_service.public_session(s), request)


@router.post("/focus-sessions/{session_id}:resume")
async def resume_session(session_id: str, request: Request, profile: dict = CurrentProfile):
    s = await focus_service.resume_focus_session(profile["id"], session_id)
    return envelope(focus_service.public_session(s), request)


@router.post("/focus-sessions/{session_id}:finish", status_code=202)
async def finish_session(session_id: str, request: Request, profile: dict = CurrentProfile):
    async def handler():
        s = await focus_service.finish_focus_session(profile["id"], session_id)
        return focus_service.public_session(s)
    return envelope(await idempotent(request, profile["id"],
                                     f"POST /focus-sessions/{session_id}:finish", handler), request)


@router.post("/focus-sessions/{session_id}:cancel")
async def cancel_session(session_id: str, request: Request, profile: dict = CurrentProfile):
    s = await focus_service.cancel_focus_session(profile["id"], session_id)
    return envelope(focus_service.public_session(s), request)


class MonitoringStartBody(BaseModel):
    display_surface: str | None = Field(default=None, max_length=20)


@router.post("/focus-sessions/{session_id}/monitoring:start")
async def start_screen_monitoring(session_id: str, body: MonitoringStartBody,
                                  request: Request, profile: dict = CurrentProfile):
    session = await focus_monitoring.start_monitoring(
        profile["id"], session_id, body.display_surface)
    return envelope(focus_service.public_session(session), request)


@router.post("/focus-sessions/{session_id}/monitoring:stop")
async def stop_screen_monitoring(session_id: str, request: Request,
                                 profile: dict = CurrentProfile):
    session = await focus_monitoring.stop_monitoring(profile["id"], session_id)
    return envelope(focus_service.public_session(session), request)


@router.post("/focus-sessions/{session_id}/frames", status_code=201)
async def upload_focus_frame(session_id: str, request: Request,
                             profile: dict = CurrentProfile):
    from ..config import settings
    declared_size = request.headers.get("content-length")
    if declared_size:
        try:
            if int(declared_size) > settings.focus_frame_max_bytes:
                raise ApiError(413, "frame_too_large", "Focus frame exceeds the allowed size.")
        except ValueError as exc:
            raise ApiError(422, "invalid_frame", "Invalid frame size header.") from exc
    # Browser Blob uploads are small (hard-capped below). Reading the complete
    # body also avoids a Starlette middleware/stream interaction that can leave
    # Chromium uploads pending indefinitely.
    content = await request.body()
    if len(content) > settings.focus_frame_max_bytes:
        raise ApiError(413, "frame_too_large", "Focus frame exceeds the allowed size.")
    frame = await focus_monitoring.store_frame(
        profile["id"], session_id,
        {
            "frame_id": request.headers.get("x-frame-id"),
            "captured_at": request.headers.get("x-captured-at"),
            "elapsed_seconds": request.headers.get("x-elapsed-seconds"),
            "width": request.headers.get("x-frame-width"),
            "height": request.headers.get("x-frame-height"),
        },
        request.headers.get("content-type", ""), content,
    )
    return envelope(frame, request)


class ConfirmBody(BaseModel):
    accepted: bool


@router.post("/verifications/{verification_id}:confirm")
async def confirm_verification(verification_id: str, body: ConfirmBody, request: Request,
                               profile: dict = CurrentProfile):
    v = await focus_service.confirm_verification(profile, verification_id, body.accepted)
    return envelope(v, request)


@router.post("/verifications/{verification_id}:recheck", status_code=202)
async def recheck_verification(verification_id: str, request: Request, profile: dict = CurrentProfile):
    v = await focus_service.recheck_verification(profile, verification_id)
    return envelope({"rechecking": True, "verification_id": v["id"]}, request)
