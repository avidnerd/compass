"""Replayable game events + in-process WebSocket fan-out."""
import asyncio
import json
import logging
from collections import defaultdict

from . import db
from .util import now_iso

logger = logging.getLogger("compass.events")

# profile_id -> set of asyncio.Queue consumed by that profile's sockets
_subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)


def subscribe(profile_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    _subscribers[profile_id].add(q)
    return q


def unsubscribe(profile_id: str, q: asyncio.Queue) -> None:
    _subscribers[profile_id].discard(q)
    if not _subscribers[profile_id]:
        _subscribers.pop(profile_id, None)


async def _audience_profiles(audience_type: str, audience_id: str) -> list[str]:
    if audience_type == "profile":
        return [audience_id]
    conn = db.get()
    if audience_type == "battle":
        cur = await conn.execute(
            "SELECT profile_id FROM battle_players WHERE battle_id = ? AND left_at IS NULL", (audience_id,))
    elif audience_type == "party":
        cur = await conn.execute("SELECT profile_id FROM party_members WHERE party_id = ?", (audience_id,))
    else:
        return []
    return [r["profile_id"] for r in await cur.fetchall()]


async def publish(audience_type: str, audience_id: str, type_: str,
                  aggregate_id: str | None = None, payload: dict | None = None) -> int:
    """Persist a game event and push it to connected, authorized sockets.

    Multiplayer payloads must already be private-data-free at the call site.
    """
    conn = db.get()
    created_at = now_iso()
    cur = await conn.execute(
        "INSERT INTO game_events (audience_type, audience_id, type, aggregate_id, payload_json, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (audience_type, audience_id, type_, aggregate_id, json.dumps(payload or {}), created_at),
    )
    event_id = cur.lastrowid
    await conn.commit()

    message = {"id": event_id, "type": type_, "aggregate_id": aggregate_id,
               "payload": payload or {}, "created_at": created_at}
    for profile_id in await _audience_profiles(audience_type, audience_id):
        for q in list(_subscribers.get(profile_id, ())):
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning("[events] dropping event for slow consumer profile=%s", profile_id[:8])
    return event_id


async def replay(profile_id: str, after_event_id: int, limit: int = 500) -> list[dict]:
    """Events this profile is authorized to see, strictly after the cursor."""
    conn = db.get()
    cur = await conn.execute(
        """
        SELECT e.* FROM game_events e
        WHERE e.id > ? AND (
          (e.audience_type = 'profile' AND e.audience_id = ?)
          OR (e.audience_type = 'battle' AND e.audience_id IN (
                SELECT battle_id FROM battle_players WHERE profile_id = ?))
          OR (e.audience_type = 'party' AND e.audience_id IN (
                SELECT party_id FROM party_members WHERE profile_id = ?))
        )
        ORDER BY e.id ASC LIMIT ?
        """,
        (after_event_id, profile_id, profile_id, profile_id, limit),
    )
    rows = await cur.fetchall()
    return [
        {"id": r["id"], "type": r["type"], "aggregate_id": r["aggregate_id"],
         "payload": json.loads(r["payload_json"]), "created_at": r["created_at"]}
        for r in rows
    ]
