"""Persisted background jobs consumed by an in-process asyncio queue.

Concurrency limits (from the plan):
- four local workers total;
- provider round-trips are bounded by bridge._semaphore (2);
- OpenRouter is bounded by openrouter._llm_semaphore (1) plus a per-profile
  lock, so one profile can't monopolize the free tier.
"""
import asyncio
import json
import logging
from collections.abc import Awaitable, Callable

from . import db, events
from .util import new_id, now_iso

logger = logging.getLogger("compass.jobs")

WORKER_COUNT = 4

_queue: asyncio.Queue[str] = asyncio.Queue()
_workers: list[asyncio.Task] = []
_handlers: dict[str, Callable[[dict], Awaitable[dict | None]]] = {}


def register(job_type: str):
    def deco(fn):
        _handlers[job_type] = fn
        return fn
    return deco


async def job_row(job_id: str) -> dict | None:
    cur = await db.get().execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = await cur.fetchone()
    if row is None:
        return None
    d = dict(row)
    d["payload"] = json.loads(d.pop("payload_json") or "{}")
    return d


def public_view(job: dict) -> dict:
    return {
        "id": job["id"], "type": job["type"], "state": job["state"],
        "progress": job["progress"], "error_code": job["error_code"],
        "retry_count": job["retry_count"], "result_type": job["result_type"],
        "result_id": job["result_id"], "created_at": job["created_at"],
        "started_at": job["started_at"], "finished_at": job["finished_at"],
    }


async def enqueue(job_type: str, profile_id: str | None, payload: dict) -> dict:
    job_id = new_id()
    ts = now_iso()
    await db.get().execute(
        "INSERT INTO jobs (id, profile_id, type, state, payload_json, created_at, updated_at)"
        " VALUES (?, ?, ?, 'queued', ?, ?, ?)",
        (job_id, profile_id, job_type, json.dumps(payload), ts, ts),
    )
    await db.get().commit()
    await _queue.put(job_id)
    job = await job_row(job_id)
    if profile_id:
        await events.publish("profile", profile_id, "job.updated", job_id, public_view(job))
    return job


async def update_job(job_id: str, **fields) -> None:
    fields["updated_at"] = now_iso()
    cols = ", ".join(f"{k} = ?" for k in fields)
    await db.get().execute(f"UPDATE jobs SET {cols} WHERE id = ?", (*fields.values(), job_id))
    await db.get().commit()
    job = await job_row(job_id)
    if job and job["profile_id"]:
        await events.publish("profile", job["profile_id"], "job.updated", job_id, public_view(job))


async def set_progress(job_id: str, progress: float) -> None:
    await update_job(job_id, progress=round(progress, 3))


async def _run_one(job_id: str) -> None:
    job = await job_row(job_id)
    if job is None or job["state"] not in ("queued", "running"):
        return
    await update_job(job_id, state="running", started_at=now_iso())
    handler = _handlers.get(job["type"])
    if handler is None:
        await update_job(job_id, state="failed", error_code="unknown_job_type", finished_at=now_iso())
        return
    try:
        result = await handler(job) or {}
        await update_job(
            job_id, state="succeeded", progress=1.0, finished_at=now_iso(),
            result_type=result.get("result_type"), result_id=result.get("result_id"),
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        # Redacted, safe error code only — never provider payloads.
        code = getattr(exc, "code", None) or type(exc).__name__
        logger.exception("[jobs] job %s (%s) failed", job_id[:8], job["type"])
        await update_job(job_id, state="failed", error_code=str(code)[:80], finished_at=now_iso())


async def _worker(n: int) -> None:
    while True:
        job_id = await _queue.get()
        try:
            await _run_one(job_id)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("[jobs] worker %d crashed on job %s", n, job_id[:8])
        finally:
            _queue.task_done()


async def resume_jobs() -> int:
    """On startup: interrupted running jobs return to queued; requeue everything queued."""
    conn = db.get()
    await conn.execute(
        "UPDATE jobs SET state = 'queued', retry_count = retry_count + 1, updated_at = ?"
        " WHERE state = 'running'", (now_iso(),))
    await conn.commit()
    cur = await conn.execute("SELECT id FROM jobs WHERE state = 'queued' ORDER BY created_at")
    rows = await cur.fetchall()
    for row in rows:
        await _queue.put(row["id"])
    return len(rows)


def start_workers() -> None:
    if _workers:
        return
    for n in range(WORKER_COUNT):
        _workers.append(asyncio.create_task(_worker(n)))


async def stop_workers() -> None:
    for t in _workers:
        t.cancel()
    for t in _workers:
        try:
            await t
        except asyncio.CancelledError:
            pass
    _workers.clear()
