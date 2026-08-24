"""Daily companion postcards: at most one per profile per local day."""
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from .. import db, jobs, llm, openrouter
from ..util import now_iso
from . import character as character_service

logger = logging.getLogger("compass.postcards")

CHECK_INTERVAL_SECONDS = 3600


def _local_day(tz_name: str) -> str:
    try:
        return datetime.now(ZoneInfo(tz_name)).date().isoformat()
    except Exception:
        return datetime.utcnow().date().isoformat()


@jobs.register("daily_postcard")
async def run_daily_postcard(job: dict) -> dict:
    profile_id = job["profile_id"]
    day = job["payload"]["day"]
    cur = await db.get().execute(
        "SELECT * FROM character_memories WHERE profile_id = ? AND kind = 'postcard' AND created_at >= ?",
        (profile_id, day))
    if await cur.fetchone():
        return {}
    try:
        ch = await character_service.get_character(profile_id, apply_drift=False)
    except Exception:
        return {}
    # High-level events only: counts and outcomes, no titles.
    cur = await db.get().execute(
        """SELECT COUNT(*) AS n, AVG(focus_score) AS avg_score FROM focus_sessions
           WHERE profile_id = ? AND state = 'completed' AND finished_at >= ?""",
        (profile_id, day))
    row = await cur.fetchone()
    if not row or not row["n"]:
        return {}
    safe_events = [f"{row['n']} focus session(s) completed",
                   f"average focus score {round(row['avg_score'] or 0)}"]
    persona = {"name": ch["name"], "personality": ch["personality"], "voice_tone": ch["voice_tone"]}
    try:
        postcard, _model = await llm.generate_daily_postcard(profile_id, persona, safe_events, day)
    except (openrouter.FreeModelUnavailable, openrouter.LLMOutputInvalid):
        postcard = llm.fallback_postcard(persona, safe_events)
    await character_service.record_memory(profile_id, kind="postcard", text=postcard.text)
    return {"result_type": "memory", "result_id": profile_id}


async def postcard_loop() -> None:
    """Hourly sweep: enqueue at most one postcard job per profile per local day."""
    while True:
        try:
            cur = await db.get().execute("SELECT id, timezone FROM profiles")
            for row in await cur.fetchall():
                day = _local_day(row["timezone"])
                c2 = await db.get().execute(
                    "SELECT 1 FROM character_memories WHERE profile_id = ? AND kind = 'postcard' AND created_at >= ?",
                    (row["id"], day))
                if await c2.fetchone():
                    continue
                c3 = await db.get().execute(
                    "SELECT 1 FROM jobs WHERE profile_id = ? AND type = 'daily_postcard'"
                    " AND state IN ('queued','running') LIMIT 1", (row["id"],))
                if await c3.fetchone():
                    continue
                c4 = await db.get().execute(
                    "SELECT 1 FROM focus_sessions WHERE profile_id = ? AND state = 'completed' AND finished_at >= ? LIMIT 1",
                    (row["id"], day))
                if await c4.fetchone():
                    await jobs.enqueue("daily_postcard", row["id"], {"day": day})
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("[postcards] sweep failed")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
