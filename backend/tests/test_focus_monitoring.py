"""Screen-monitoring lifecycle, ownership, and raw-frame cleanup."""
import uuid
from pathlib import Path

from app import db, focus_monitoring
from conftest import create_profile, wait_until


def frame_headers(frame_id: str) -> dict[str, str]:
    return {
        "Content-Type": "image/jpeg",
        "X-Frame-Id": frame_id,
        "X-Captured-At": "2026-07-26T12:00:00Z",
        "X-Elapsed-Seconds": "0",
        "X-Frame-Width": "1280",
        "X-Frame-Height": "720",
    }


async def test_monitored_session_upload_analyze_and_cleanup(env, monkeypatch):
    await create_profile(env.client)
    started = (await env.client.post(
        "/api/v1/focus-sessions", json={"planned_minutes": 25})).json()["data"]
    sid = started["id"]

    monitor = await env.client.post(
        f"/api/v1/focus-sessions/{sid}/monitoring:start",
        json={"display_surface": "monitor"})
    assert monitor.status_code == 200
    assert monitor.json()["data"]["monitoring_status"] == "active"

    upload = await env.client.post(
        f"/api/v1/focus-sessions/{sid}/frames",
        headers=frame_headers(str(uuid.uuid4())), content=b"private-jpeg-bytes")
    assert upload.status_code == 201, upload.text
    cur = await db.get().execute(
        "SELECT storage_path FROM focus_frames WHERE session_id = ?", (sid,))
    raw_path = Path((await cur.fetchone())["storage_path"])
    assert raw_path.is_file()

    async def fake_analyze_batch(_profile_id, _session_id, _context, frames):
        return ([{
            "frame_id": frame["id"], "classification": "direct_work", "confidence": 0.92,
            "visible_activity": "Editing the declared task",
            "relevance_reason": "Visible work matches the task",
            "contains_sensitive_content": False,
        } for frame in frames], "example/vision:free")

    monkeypatch.setattr(focus_monitoring, "_analyze_batch", fake_analyze_batch)
    finished = await env.client.post(f"/api/v1/focus-sessions/{sid}:finish")
    assert finished.status_code == 202

    async def analyzed():
        detail = (await env.client.get(f"/api/v1/focus-sessions/{sid}")).json()["data"]
        return detail if detail["session"]["focus_evaluation"] else None

    detail = await wait_until(analyzed)
    evaluation = detail["session"]["focus_evaluation"]
    assert evaluation["status"] == "analyzed"
    assert evaluation["frames_captured"] == 1
    assert evaluation["frames_analyzed"] == 1
    assert evaluation["model_id"] == "example/vision:free"
    assert not raw_path.exists(), "raw screenshot must be deleted after analysis"


async def test_sampling_pauses_and_cancel_removes_raw_frame(env):
    await create_profile(env.client)
    session = (await env.client.post(
        "/api/v1/focus-sessions", json={"planned_minutes": 25})).json()["data"]
    sid = session["id"]
    await env.client.post(f"/api/v1/focus-sessions/{sid}/monitoring:start",
                          json={"display_surface": "window"})
    upload = await env.client.post(
        f"/api/v1/focus-sessions/{sid}/frames",
        headers=frame_headers(str(uuid.uuid4())), content=b"temporary-private-frame")
    assert upload.status_code == 201
    cur = await db.get().execute(
        "SELECT storage_path FROM focus_frames WHERE session_id = ?", (sid,))
    raw_path = Path((await cur.fetchone())["storage_path"])

    paused = await env.client.post(f"/api/v1/focus-sessions/{sid}:pause")
    assert paused.json()["data"]["monitoring_status"] == "paused"
    rejected = await env.client.post(
        f"/api/v1/focus-sessions/{sid}/frames",
        headers=frame_headers(str(uuid.uuid4())), content=b"must-not-store")
    assert rejected.status_code == 409

    canceled = await env.client.post(f"/api/v1/focus-sessions/{sid}:cancel")
    assert canceled.status_code == 200
    assert canceled.json()["data"]["monitoring_status"] == "canceled"
    assert not raw_path.exists(), "cancel must remove raw screenshots"


def test_unclear_frames_are_not_described_as_fragmented_attention():
    session = {
        "id": str(uuid.uuid4()), "started_at": "2026-07-26T12:00:00Z",
        "finished_at": "2026-07-26T12:01:00Z", "paused_total_seconds": 0,
        "frames_captured": 2,
    }
    frames = [
        {"id": str(uuid.uuid4()), "elapsed_seconds": 0, "classification": "unclear",
         "confidence": 0.4, "visible_activity": "Text too small to read"},
        {"id": str(uuid.uuid4()), "elapsed_seconds": 30, "classification": "unclear",
         "confidence": 0.4, "visible_activity": "Task relevance unclear"},
    ]
    evaluation = focus_monitoring._metrics(session, frames, "analyzed", "vision:free")
    assert evaluation["summary"]["headline"] == \
        "Visible activity was too ambiguous to score confidently"
    assert evaluation["recovery"]["distraction_episodes"] == 0
