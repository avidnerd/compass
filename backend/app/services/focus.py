"""Focus sessions: authoritative timers, verification pipeline, rewards."""
import json
import logging

from .. import db, events, jobs, llm, openrouter, telemetry
from ..errors import ApiError, forbidden, not_found
from ..util import new_id, now, now_iso, parse_iso
from . import character as character_service
from . import quests as quest_service
from . import rewards

logger = logging.getLogger("compass.focus")

VERIFY_THRESHOLD = 0.50
REJECT_THRESHOLD = 0.35
RECHECK_COOLDOWN_SECONDS = 120


def public_session(row: dict) -> dict:
    d = dict(row)
    d["demo"] = bool(d.get("demo"))
    d["monitoring_enabled"] = bool(d.get("monitoring_enabled"))
    raw_evaluation = d.pop("focus_evaluation_json", None)
    d["focus_evaluation"] = json.loads(raw_evaluation) if raw_evaluation else None
    from ..config import settings
    d["monitoring_interval_seconds"] = settings.focus_frame_interval_seconds
    d["server_time"] = now_iso()
    return d


async def session_row(profile_id: str, session_id: str) -> dict:
    cur = await db.get().execute("SELECT * FROM focus_sessions WHERE id = ?", (session_id,))
    row = await cur.fetchone()
    if row is None:
        raise not_found("focus session")
    if row["profile_id"] != profile_id:
        raise forbidden()
    return dict(row)


async def list_sessions(profile_id: str, limit: int = 50, cursor: str | None = None) -> list[dict]:
    sql = "SELECT * FROM focus_sessions WHERE profile_id = ?"
    params: list = [profile_id]
    if cursor:
        sql += " AND created_at < ?"
        params.append(cursor)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(min(limit, 100))
    cur = await db.get().execute(sql, params)
    return [public_session(dict(r)) for r in await cur.fetchall()]


async def _subgoal(profile_id: str, subgoal_id: str) -> dict:
    cur = await db.get().execute("SELECT * FROM subgoals WHERE id = ?", (subgoal_id,))
    row = await cur.fetchone()
    if row is None:
        raise not_found("subgoal")
    if row["profile_id"] != profile_id:
        raise forbidden()
    return dict(row)


async def start_focus_session(profile: dict, body: dict) -> dict:
    profile_id = profile["id"]
    planned_minutes = int(body.get("planned_minutes") or 25)
    demo = bool(body.get("demo"))
    if demo:
        planned_minutes = 1
    planned_seconds = max(60, min(planned_minutes, 180) * 60)

    subgoal_id = body.get("subgoal_id")
    quest_id = body.get("quest_id")
    evidence_specs: list[str] = ["manual_confirmation"]
    if subgoal_id:
        sg = await _subgoal(profile_id, subgoal_id)
        quest_id = sg["quest_id"]
        evidence_specs = json.loads(sg["evidence_specs_json"])

    cur = await db.get().execute(
        "SELECT id FROM focus_sessions WHERE profile_id = ? AND state IN ('running','paused','ending')",
        (profile_id,))
    if await cur.fetchone():
        raise ApiError(409, "session_already_active", "You already have an active focus session.")

    session_id = new_id()
    ts = now_iso()
    await db.get().execute(
        """INSERT INTO focus_sessions (id, profile_id, quest_id, subgoal_id, state,
             planned_seconds, started_at, demo, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'running', ?, ?, ?, ?, ?)""",
        (session_id, profile_id, quest_id, subgoal_id, planned_seconds, ts,
         1 if demo else 0, ts, ts))
    if subgoal_id:
        await db.get().execute(
            "UPDATE subgoals SET state = 'in_progress', updated_at = ? WHERE id = ? AND state = 'todo'",
            (ts, subgoal_id))
    await db.get().commit()

    # Baseline uses cached telemetry only — no forced provider calls at start.
    try:
        await telemetry.capture_snapshot(profile, evidence_specs, "baseline", session_id)
    except Exception as exc:
        logger.warning("[focus] baseline snapshot degraded: %s", type(exc).__name__)

    session = await session_row(profile_id, session_id)
    await events.publish("profile", profile_id, "focus.updated", session_id, public_session(session))
    return session


async def pause_focus_session(profile_id: str, session_id: str) -> dict:
    s = await session_row(profile_id, session_id)
    if s["state"] != "running":
        raise ApiError(409, "invalid_state", f"Cannot pause a session in state {s['state']}.")
    await db.get().execute(
        "UPDATE focus_sessions SET state = 'paused', paused_at = ?, updated_at = ? WHERE id = ?",
        (now_iso(), now_iso(), session_id))
    await db.get().execute(
        "UPDATE focus_sessions SET monitoring_status = 'paused' "
        "WHERE id = ? AND monitoring_status = 'active'", (session_id,))
    await db.get().commit()
    s = await session_row(profile_id, session_id)
    await events.publish("profile", profile_id, "focus.updated", session_id, public_session(s))
    return s


async def resume_focus_session(profile_id: str, session_id: str) -> dict:
    s = await session_row(profile_id, session_id)
    if s["state"] != "paused":
        raise ApiError(409, "invalid_state", f"Cannot resume a session in state {s['state']}.")
    paused_seconds = int((now() - parse_iso(s["paused_at"])).total_seconds()) if s["paused_at"] else 0
    await db.get().execute(
        """UPDATE focus_sessions SET state = 'running', paused_at = NULL,
             paused_total_seconds = paused_total_seconds + ?, updated_at = ? WHERE id = ?""",
        (max(0, paused_seconds), now_iso(), session_id))
    await db.get().execute(
        "UPDATE focus_sessions SET monitoring_status = 'active' "
        "WHERE id = ? AND monitoring_status = 'paused'", (session_id,))
    await db.get().commit()
    s = await session_row(profile_id, session_id)
    await events.publish("profile", profile_id, "focus.updated", session_id, public_session(s))
    return s


async def cancel_focus_session(profile_id: str, session_id: str) -> dict:
    s = await session_row(profile_id, session_id)
    if s["state"] not in ("running", "paused"):
        raise ApiError(409, "invalid_state", f"Cannot cancel a session in state {s['state']}.")
    await db.get().execute(
        """UPDATE focus_sessions SET state = 'canceled', finished_at = ?,
             monitoring_status = CASE WHEN monitoring_enabled = 1 THEN 'canceled'
                                      ELSE monitoring_status END,
             monitoring_stopped_at = CASE WHEN monitoring_enabled = 1 THEN ?
                                          ELSE monitoring_stopped_at END,
             updated_at = ? WHERE id = ?""",
        (now_iso(), now_iso(), now_iso(), session_id))
    if s["subgoal_id"]:
        await db.get().execute(
            "UPDATE subgoals SET state = 'in_progress', updated_at = ? WHERE id = ? AND state = 'verifying'",
            (now_iso(), s["subgoal_id"]))
    await db.get().commit()
    from .. import focus_monitoring
    await focus_monitoring.cleanup_session_frames(session_id)
    s = await session_row(profile_id, session_id)
    await events.publish("profile", profile_id, "focus.updated", session_id, public_session(s))
    return s


async def finish_focus_session(profile_id: str, session_id: str) -> dict:
    """Freeze timing idempotently and queue the verification job."""
    s = await session_row(profile_id, session_id)
    if s["state"] in ("ending", "completed"):
        return s  # idempotent: duplicate finish returns current state
    if s["state"] not in ("running", "paused"):
        raise ApiError(409, "invalid_state", f"Cannot finish a session in state {s['state']}.")
    paused_extra = 0
    if s["state"] == "paused" and s["paused_at"]:
        paused_extra = max(0, int((now() - parse_iso(s["paused_at"])).total_seconds()))
    await db.get().execute(
        """UPDATE focus_sessions SET state = 'ending', finished_at = ?, paused_at = NULL,
             paused_total_seconds = paused_total_seconds + ?,
             monitoring_status = CASE WHEN monitoring_enabled = 1 THEN 'completed'
                                      ELSE monitoring_status END,
             monitoring_stopped_at = CASE WHEN monitoring_enabled = 1 THEN ?
                                          ELSE monitoring_stopped_at END,
             updated_at = ?
           WHERE id = ? AND state IN ('running','paused')""",
        (now_iso(), paused_extra, now_iso(), now_iso(), session_id))
    if s["subgoal_id"]:
        await db.get().execute(
            "UPDATE subgoals SET state = 'verifying', updated_at = ? WHERE id = ?",
            (now_iso(), s["subgoal_id"]))
    await db.get().commit()
    await jobs.enqueue("session_verify", profile_id, {"session_id": session_id})
    s = await session_row(profile_id, session_id)
    await events.publish("profile", profile_id, "focus.updated", session_id, public_session(s))
    return s


def _timing(s: dict) -> tuple[int, int]:
    """(active_seconds, total_seconds) from authoritative server timestamps."""
    total = int((parse_iso(s["finished_at"]) - parse_iso(s["started_at"])).total_seconds())
    total = max(0, total)
    active = max(0, total - (s["paused_total_seconds"] or 0))
    return active, total


async def _snapshot(session_id: str, phase: str) -> dict | None:
    cur = await db.get().execute(
        "SELECT * FROM telemetry_snapshots WHERE session_id = ? AND phase = ? ORDER BY captured_at DESC",
        (session_id, phase))
    row = await cur.fetchone()
    if row is None:
        return None
    return {"id": row["id"], "phase": row["phase"], "metrics": json.loads(row["metrics_json"]),
            "generations": json.loads(row["generations_json"]), "captured_at": row["captured_at"]}


async def _store_evidence(profile_id: str, session_id: str, items: list[dict]) -> list[dict]:
    conn = db.get()
    stored = []
    for item in items[:40]:
        eid = new_id()
        await conn.execute(
            """INSERT INTO evidence_items (id, profile_id, session_id, source, event_type, occurred_at,
                 external_ref_hash, content_hash, summary, metric_delta_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (eid, profile_id, session_id, item["source"], item["event_type"], item.get("occurred_at"),
             item.get("external_ref_hash"), item.get("content_hash"), item["summary"],
             json.dumps(item.get("metric_delta") or {}), now_iso()))
        stored.append({**item, "id": eid})
    await conn.commit()
    return stored


MAX_CONTENT_EXCERPTS = 3


async def _attach_content_excerpts(profile: dict, stored: list[dict]) -> None:
    """For changed docs/sheets/slides, fetch a bounded excerpt of the CURRENT
    content so the model can judge the acceptance criterion against real text.

    The excerpt lives only on the in-memory dicts passed to the LLM; the
    database keeps just a content hash. Fetch failures are non-fatal — the
    evidence card then honestly says content was not readable.
    """
    from ..config import settings as app_settings
    from ..util import sha256_hex
    fetchers = {
        "document_content_changed": telemetry.summarize_document,
        "sheet_values_changed": telemetry.summarize_sheet,
        "presentation_content_changed": telemetry.summarize_presentation,
    }
    cap = app_settings.verify_excerpt_chars
    attached = 0
    for item in stored:
        if attached >= MAX_CONTENT_EXCERPTS:
            break
        fetcher = fetchers.get(item.get("event_type") or "")
        ref = item.get("_ref")
        if fetcher is None or not ref:
            continue
        try:
            text = await fetcher(profile, {"id": ref}, cap)
        except Exception:
            text = None
        if not text:
            continue
        excerpt = text[:cap]
        item["excerpt"] = excerpt
        content_hash = sha256_hex(excerpt)
        item["content_hash"] = content_hash
        debug_excerpt = excerpt if app_settings.debug_evidence else None
        await db.get().execute(
            "UPDATE evidence_items SET content_hash = ?, debug_excerpt = ? WHERE id = ?",
            (content_hash, debug_excerpt, item["id"]))
        attached += 1
    await db.get().commit()


async def run_verification(profile: dict, session: dict, force_refresh: bool = True) -> dict:
    """Extract evidence and (if a free model is available) interpret it."""
    profile_id = profile["id"]
    session_id = session["id"]
    subgoal = None
    evidence_specs = ["manual_confirmation"]
    if session["subgoal_id"]:
        subgoal = await _subgoal(profile_id, session["subgoal_id"])
        evidence_specs = json.loads(subgoal["evidence_specs_json"])

    baseline = await _snapshot(session_id, "baseline") or {"metrics": {}, "generations": {}}
    final = await telemetry.capture_snapshot(
        profile, evidence_specs, "final", session_id,
        window_start=parse_iso(session["started_at"]))

    window = (session["started_at"], session["finished_at"] or now_iso())
    items = telemetry.extract_evidence(baseline, final, evidence_specs, window)
    stored = await _store_evidence(profile_id, session_id, items)
    unavailable = telemetry.unavailable_specs(evidence_specs, baseline, final)
    await _attach_content_excerpts(profile, stored)

    manual_only = evidence_specs == ["manual_confirmation"]
    result, confidence, explanation, observed, not_observed, model_id = (
        "needs_confirmation", 0.5, "", "", "", None)

    if manual_only:
        explanation = "This step is verified by you — no telemetry is involved."
        observed = "A completed focus session."
        not_observed = "Automatic evidence (this step is manual)."
    elif subgoal is not None:
        snapshot_key = {"session": session_id, "final_snapshot": final["id"],
                        "evidence": sorted(e["external_ref_hash"] or "" for e in items)}
        quest_goal = None
        if session["quest_id"]:
            cur = await db.get().execute("SELECT goal FROM quests WHERE id = ?", (session["quest_id"],))
            row = await cur.fetchone()
            quest_goal = row["goal"] if row else None
        try:
            draft, model_id = await llm.evaluate_subgoal(
                profile_id, {"title": subgoal["title"],
                             "acceptance_criterion": subgoal["acceptance_criterion"],
                             "rationale": subgoal["rationale"],
                             "quest_goal": quest_goal},
                stored, snapshot_key)
            confidence = draft.confidence
            explanation = draft.explanation
            observed = draft.observed
            not_observed = draft.not_observed
            # Purely confidence-gated: the model's calibration instructions
            # (see llm.evaluate_subgoal) already tie confidence to how well
            # the evidence demonstrates completion, so >=50% is accepted
            # outright rather than additionally requiring completed/items.
            if confidence >= VERIFY_THRESHOLD:
                result = "verified"
            elif confidence <= REJECT_THRESHOLD:
                result = "not_completed"
            else:
                result = "needs_confirmation"
        except (openrouter.FreeModelUnavailable, openrouter.LLMOutputInvalid):
            result = "needs_confirmation"
            explanation = ("Free AI is temporarily unavailable, so Compass shows the raw evidence "
                           "and asks you instead.")
            observed = f"{len(items)} evidence item(s) extracted deterministically."
            not_observed = "An AI interpretation of the evidence."
    if unavailable:
        not_observed = (not_observed + " " if not_observed else "") + \
            f"Could not check: {', '.join(unavailable)}."

    sources = sorted({e["source"] for e in stored})
    verification_id = new_id()
    ts = now_iso()
    await db.get().execute(
        """INSERT INTO verifications (id, profile_id, session_id, subgoal_id, result, confidence,
             explanation, observed, not_observed, sources_json, model_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(session_id) DO UPDATE SET
             result = excluded.result, confidence = excluded.confidence,
             explanation = excluded.explanation, observed = excluded.observed,
             not_observed = excluded.not_observed, sources_json = excluded.sources_json,
             model_id = excluded.model_id, last_recheck_at = ?, updated_at = ?""",
        (verification_id, profile_id, session_id, session["subgoal_id"], result, confidence,
         explanation, observed, not_observed, json.dumps(sources), model_id, ts, ts, ts, ts))
    await db.get().commit()
    cur = await db.get().execute("SELECT * FROM verifications WHERE session_id = ?", (session_id,))
    return dict(await cur.fetchone())


async def _complete_session(profile: dict, session: dict, verification: dict,
                            completion: float, human_confirmed: bool) -> None:
    """Score, reward (idempotently), advance subgoal, notify multiplayer."""
    profile_id = profile["id"]
    session_id = session["id"]
    active, total = _timing(session)
    prior = await rewards.prior_focus_scores(profile_id, session_id)
    score = rewards.calculate_focus_score(
        active, session["planned_seconds"], session["paused_total_seconds"] or 0, total,
        completion, prior)

    await db.get().execute(
        "UPDATE focus_sessions SET state = 'completed', focus_score = ?, updated_at = ? WHERE id = ?",
        (score, now_iso(), session_id))
    await db.get().commit()

    cur = await db.get().execute("SELECT * FROM evidence_items WHERE session_id = ?", (session_id,))
    evidence = [dict(r) for r in await cur.fetchall()]
    primary_stat = rewards.primary_stat_for_evidence(evidence)
    completed = completion > 0

    outcome = verification["result"]
    reward_summary = None
    if completed:
        r = rewards.session_rewards(score, primary_stat, human_confirmed)
        reward_summary = await rewards.apply_rewards(
            profile_id, f"session:{session_id}", r["xp"], r["care_points"], r["stats"],
            reason=f"Focus session ({outcome})")
        if session["subgoal_id"]:
            await db.get().execute(
                "UPDATE subgoals SET state = 'completed', updated_at = ? WHERE id = ?",
                (now_iso(), session["subgoal_id"]))
            await db.get().commit()
            if session["quest_id"]:
                await quest_service.maybe_complete_quest(profile_id, session["quest_id"])
    else:
        # Gentle recovery: no punishment, subgoal returns to in_progress.
        await rewards.apply_rewards(profile_id, f"session:{session_id}", 5, 0, {},
                                    reason="Focus session (effort logged)")
        if session["subgoal_id"]:
            await db.get().execute(
                "UPDATE subgoals SET state = 'in_progress', updated_at = ? WHERE id = ?",
                (now_iso(), session["subgoal_id"]))
            await db.get().commit()

    session = await session_row(profile_id, session_id)
    await events.publish("profile", profile_id, "focus.updated", session_id, public_session(session))
    await events.publish("profile", profile_id, "verification.updated", verification["id"], {
        "result": outcome, "session_id": session_id, "focus_score": score,
        "human_confirmed": human_confirmed})

    reaction_outcome = "verified" if (completed and not human_confirmed and outcome == "verified") \
        else ("needs_confirmation" if outcome == "needs_confirmation" and not human_confirmed
              else ("verified" if completed else "not_completed"))
    category = "general"
    if session["quest_id"]:
        cur = await db.get().execute("SELECT category FROM quests WHERE id = ?", (session["quest_id"],))
        row = await cur.fetchone()
        if row:
            category = row["category"]
    await character_service.react(profile_id, "session_finished", reaction_outcome, category,
                                  reward_summary)

    # Focus rooms are presence-only: a verified session touches no shared state.


@jobs.register("session_verify")
async def run_session_verify(job: dict) -> dict:
    from . import profiles as profile_service
    profile = await profile_service.get_profile(job["profile_id"])
    session = await session_row(profile["id"], job["payload"]["session_id"])
    if session["state"] == "completed":
        return {"result_type": "focus_session", "result_id": session["id"]}
    if session["state"] != "ending":
        raise ApiError(409, "invalid_state", "Session is not awaiting verification.")
    if not session.get("focus_evaluation_json"):
        from .. import focus_monitoring
        await jobs.set_progress(job["id"], 0.1)
        await focus_monitoring.analyze_session(profile["id"], session)
    await jobs.set_progress(job["id"], 0.4)
    verification = await run_verification(profile, session)
    await jobs.set_progress(job["id"], 0.8)
    if verification["result"] == "verified":
        await _complete_session(profile, session, verification, completion=1.0, human_confirmed=False)
    elif verification["result"] == "not_completed":
        await _complete_session(profile, session, verification, completion=0.0, human_confirmed=False)
    else:
        # needs_confirmation: keep the session in 'ending' until the user answers.
        if session["subgoal_id"]:
            await db.get().execute(
                "UPDATE subgoals SET state = 'needs_confirmation', updated_at = ? WHERE id = ?",
                (now_iso(), session["subgoal_id"]))
            await db.get().commit()
        await events.publish("profile", profile["id"], "verification.updated", verification["id"], {
            "result": "needs_confirmation", "session_id": session["id"]})
    return {"result_type": "verification", "result_id": verification["id"]}


async def confirm_verification(profile: dict, verification_id: str, accepted: bool) -> dict:
    profile_id = profile["id"]
    cur = await db.get().execute("SELECT * FROM verifications WHERE id = ?", (verification_id,))
    row = await cur.fetchone()
    if row is None:
        raise not_found("verification")
    v = dict(row)
    if v["profile_id"] != profile_id:
        raise forbidden()
    if v["human_confirmed"] is not None:
        raise ApiError(409, "already_confirmed", "This verification was already answered.")
    session = await session_row(profile_id, v["session_id"])
    if session["state"] == "completed":
        raise ApiError(409, "already_confirmed", "This session is already completed.")

    await db.get().execute(
        "UPDATE verifications SET human_confirmed = ?, updated_at = ? WHERE id = ?",
        (1 if accepted else 0, now_iso(), verification_id))
    await db.get().commit()
    v["human_confirmed"] = 1 if accepted else 0
    if accepted:
        await _complete_session(profile, session, v, completion=0.75, human_confirmed=True)
    else:
        await _complete_session(profile, session, v, completion=0.0, human_confirmed=True)
    cur = await db.get().execute("SELECT * FROM verifications WHERE id = ?", (verification_id,))
    return dict(await cur.fetchone())


async def recheck_verification(profile: dict, verification_id: str) -> dict:
    cur = await db.get().execute("SELECT * FROM verifications WHERE id = ?", (verification_id,))
    row = await cur.fetchone()
    if row is None:
        raise not_found("verification")
    v = dict(row)
    if v["profile_id"] != profile["id"]:
        raise forbidden()
    if v["last_recheck_at"] and (now() - parse_iso(v["last_recheck_at"])).total_seconds() < RECHECK_COOLDOWN_SECONDS:
        raise ApiError(429, "recheck_cooldown", "Please wait a couple of minutes between rechecks.")
    session = await session_row(profile["id"], v["session_id"])
    if session["state"] != "ending":
        raise ApiError(409, "invalid_state", "This session is no longer awaiting confirmation.")
    await jobs.enqueue("session_verify", profile["id"], {"session_id": session["id"]})
    return v


async def verification_for_session(profile_id: str, session_id: str) -> dict | None:
    cur = await db.get().execute("SELECT * FROM verifications WHERE session_id = ?", (session_id,))
    row = await cur.fetchone()
    if row is None:
        return None
    v = dict(row)
    if v["profile_id"] != profile_id:
        raise forbidden()
    cur = await db.get().execute("SELECT * FROM evidence_items WHERE session_id = ?", (session_id,))
    v["evidence"] = [dict(r) for r in await cur.fetchall()]
    v["sources"] = json.loads(v.pop("sources_json") or "[]")
    return v
