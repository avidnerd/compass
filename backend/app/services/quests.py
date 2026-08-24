"""Quest planning and editing. The plan proposes; the user disposes."""
import json
import logging

from .. import capabilities, db, events, jobs, llm, openrouter
from ..errors import ApiError, forbidden, not_found
from ..util import new_id, now_iso, sha256_hex

logger = logging.getLogger("compass.quests")

QUEST_STATES = ["draft", "planning", "active", "completed", "archived"]
SUBGOAL_STATES = ["todo", "in_progress", "verifying", "needs_confirmation", "completed"]


def public_subgoal(row: dict) -> dict:
    d = dict(row)
    d["evidence_specs"] = json.loads(d.pop("evidence_specs_json") or "[]")
    return d


async def quest_row(profile_id: str, quest_id: str) -> dict:
    cur = await db.get().execute("SELECT * FROM quests WHERE id = ?", (quest_id,))
    row = await cur.fetchone()
    if row is None:
        raise not_found("quest")
    if row["profile_id"] != profile_id:
        raise forbidden()
    return dict(row)


async def quest_with_subgoals(profile_id: str, quest_id: str) -> dict:
    quest = await quest_row(profile_id, quest_id)
    cur = await db.get().execute(
        "SELECT * FROM subgoals WHERE quest_id = ? ORDER BY position", (quest_id,))
    quest["subgoals"] = [public_subgoal(dict(r)) for r in await cur.fetchall()]
    quest["targets"] = json.loads(quest.pop("targets_json") or "{}")
    return quest


async def list_quests(profile_id: str, limit: int = 50, cursor: str | None = None) -> list[dict]:
    sql = "SELECT * FROM quests WHERE profile_id = ?"
    params: list = [profile_id]
    if cursor:
        sql += " AND created_at < ?"
        params.append(cursor)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(min(limit, 100))
    cur = await db.get().execute(sql, params)
    out = []
    for r in await cur.fetchall():
        q = dict(r)
        q["targets"] = json.loads(q.pop("targets_json") or "{}")
        c2 = await db.get().execute(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN state='completed' THEN 1 ELSE 0 END) AS done"
            " FROM subgoals WHERE quest_id = ?", (q["id"],))
        counts = await c2.fetchone()
        q["subgoal_total"] = counts["total"]
        q["subgoal_done"] = counts["done"] or 0
        out.append(q)
    return out


def available_evidence_types() -> list[str]:
    """Evidence enums whose connector currently has the needed capability.
    manual_confirmation is always available."""
    reg = capabilities.current_registry()
    if reg is None:
        return ["manual_confirmation"]
    needed = {
        "file_created": "drive.list_files", "file_modified": "drive.list_files",
        "document_content_changed": "drive.list_files", "sheet_values_changed": "drive.list_files",
        "presentation_content_changed": "drive.list_files", "email_sent": "gmail.list_messages",
        "calendar_event_completed": "calendar.list_events",
        "github_commit_created": "github.get_commits",
        "github_pull_request_opened": "github.get_pull_requests",
        "github_pull_request_merged": "github.get_pull_requests",
        "github_checks_passed": "github.get_checks",
        "meet_attended": "meet.list_conference_records",
    }
    out = [e for e, cap in needed.items() if reg.resolve(cap) is not None]
    out.append("manual_confirmation")
    return out


async def create_quest(profile_id: str, body: dict) -> dict:
    goal = (body.get("goal") or "").strip()
    if not goal:
        raise ApiError(422, "invalid_request", "A goal is required.")
    quest_id = new_id()
    ts = now_iso()
    await db.get().execute(
        """INSERT INTO quests (id, profile_id, goal, meaning, state, target_date,
             session_length_minutes, share_category, targets_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?)""",
        (quest_id, profile_id, goal[:300], (body.get("meaning") or "")[:300] or None,
         body.get("target_date"), int(body.get("session_length_minutes") or 25),
         1 if body.get("share_category") else 0,
         json.dumps(body.get("targets") or {}), ts, ts))
    await db.get().commit()

    if body.get("plan", True):
        await db.get().execute("UPDATE quests SET state = 'planning', updated_at = ? WHERE id = ?",
                               (now_iso(), quest_id))
        await db.get().commit()
        await jobs.enqueue("quest_plan", profile_id, {"quest_id": quest_id})
    await events.publish("profile", profile_id, "quest.updated", quest_id, {"state": "planning"})
    return await quest_with_subgoals(profile_id, quest_id)


async def _insert_plan(profile_id: str, quest_id: str, plan: llm.QuestPlan, model_id: str | None):
    conn = db.get()
    await conn.execute("DELETE FROM subgoals WHERE quest_id = ?", (quest_id,))
    ts = now_iso()
    for i, sg in enumerate(plan.subgoals):
        await conn.execute(
            """INSERT INTO subgoals (id, quest_id, profile_id, position, title, rationale,
                 acceptance_criterion, difficulty, estimated_sessions, state, evidence_specs_json,
                 manual_fallback, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'todo', ?, ?, ?, ?)""",
            (new_id(), quest_id, profile_id, i, sg.title, sg.rationale, sg.acceptance_criterion,
             sg.difficulty, sg.estimated_sessions, json.dumps(sg.evidence_types),
             sg.manual_fallback, ts, ts))
    await conn.execute(
        "UPDATE quests SET state = 'draft', category = ?, plan_model_id = ?, version = version + 1, updated_at = ? WHERE id = ?",
        (plan.category[:40] or "general", model_id, ts, quest_id))
    await conn.commit()


@jobs.register("quest_plan")
async def run_quest_plan(job: dict) -> dict:
    profile_id = job["profile_id"]
    quest_id = job["payload"]["quest_id"]
    quest = await quest_row(profile_id, quest_id)
    interests: list[str] = []
    cur = await db.get().execute("SELECT topics_json FROM interest_profiles WHERE profile_id = ?",
                                 (profile_id,))
    row = await cur.fetchone()
    if row:
        interests = [t["label"] for t in json.loads(row["topics_json"])][:5]
    evidence = available_evidence_types()
    plan_key = {"goal_hash": sha256_hex(f"{quest['goal']}|{quest['meaning']}|{quest['target_date']}"),
                "evidence": sorted(evidence)}
    model_id: str | None = None
    try:
        plan, model_id = await llm.decompose_quest(
            profile_id, quest["goal"], quest["meaning"], quest["target_date"],
            evidence, interests, plan_key)
        # Defense in depth: drop any evidence enum we can't actually observe.
        for sg in plan.subgoals:
            sg.evidence_types = [e for e in sg.evidence_types if e in evidence] or ["manual_confirmation"]
    except (openrouter.FreeModelUnavailable, openrouter.LLMOutputInvalid):
        plan = llm.fallback_quest_plan(quest["goal"])
    await _insert_plan(profile_id, quest_id, plan, model_id)
    await events.publish("profile", profile_id, "quest.updated", quest_id, {"state": "draft"})
    return {"result_type": "quest", "result_id": quest_id}


async def patch_quest(profile_id: str, quest_id: str, patch: dict) -> dict:
    quest = await quest_row(profile_id, quest_id)
    fields: dict = {}
    for key in ("goal", "meaning", "target_date"):
        if key in patch and patch[key] is not None:
            fields[key] = str(patch[key])[:300]
    if "session_length_minutes" in patch:
        fields["session_length_minutes"] = max(1, min(180, int(patch["session_length_minutes"])))
    if "share_category" in patch:
        fields["share_category"] = 1 if patch["share_category"] else 0
    if fields:
        cols = ", ".join(f"{k} = ?" for k in fields)
        await db.get().execute(
            f"UPDATE quests SET {cols}, version = version + 1, updated_at = ? WHERE id = ?",
            (*fields.values(), now_iso(), quest_id))
        await db.get().commit()

    # Full subgoal list replacement (review/edit/reorder/add/delete before activation).
    if "subgoals" in patch and isinstance(patch["subgoals"], list):
        if quest["state"] not in ("draft", "planning", "active"):
            raise ApiError(409, "quest_locked", "This quest can no longer be edited.")
        allowed_evidence = set(llm.EVIDENCE_TYPES)
        conn = db.get()
        cur = await conn.execute("SELECT id, state FROM subgoals WHERE quest_id = ?", (quest_id,))
        existing = {r["id"]: r["state"] for r in await cur.fetchall()}
        keep: set[str] = set()
        ts = now_iso()
        for i, sg in enumerate(patch["subgoals"][:12]):
            sg_id = sg.get("id") if sg.get("id") in existing else None
            evidence = [e for e in (sg.get("evidence_specs") or ["manual_confirmation"])
                        if e in allowed_evidence] or ["manual_confirmation"]
            values = (i, str(sg.get("title") or "Untitled step")[:120],
                      str(sg.get("rationale") or "")[:300],
                      str(sg.get("acceptance_criterion") or "Done when you say it's done.")[:300],
                      max(1, min(5, int(sg.get("difficulty") or 2))),
                      max(1, min(20, int(sg.get("estimated_sessions") or 1))),
                      json.dumps(evidence), str(sg.get("manual_fallback") or "Did you complete this step?")[:200], ts)
            if sg_id:
                keep.add(sg_id)
                await conn.execute(
                    """UPDATE subgoals SET position=?, title=?, rationale=?, acceptance_criterion=?,
                         difficulty=?, estimated_sessions=?, evidence_specs_json=?, manual_fallback=?,
                         updated_at=? WHERE id = ?""", (*values, sg_id))
            else:
                new_sg = new_id()
                keep.add(new_sg)
                await conn.execute(
                    """INSERT INTO subgoals (id, quest_id, profile_id, position, title, rationale,
                         acceptance_criterion, difficulty, estimated_sessions, state,
                         evidence_specs_json, manual_fallback, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'todo', ?, ?, ?, ?)""",
                    (new_sg, quest_id, profile_id, *values[:6], values[6], values[7], ts, ts))
        for sg_id, state in existing.items():
            if sg_id not in keep and state != "completed":
                await conn.execute("DELETE FROM subgoals WHERE id = ?", (sg_id,))
        await conn.execute("UPDATE quests SET version = version + 1, updated_at = ? WHERE id = ?",
                           (ts, quest_id))
        await conn.commit()
    await events.publish("profile", profile_id, "quest.updated", quest_id, {"state": "edited"})
    return await quest_with_subgoals(profile_id, quest_id)


async def activate_quest(profile_id: str, quest_id: str) -> dict:
    quest = await quest_row(profile_id, quest_id)
    if quest["state"] not in ("draft", "planning"):
        raise ApiError(409, "invalid_state", f"Cannot activate a quest in state {quest['state']}.")
    cur = await db.get().execute("SELECT COUNT(*) AS n FROM subgoals WHERE quest_id = ?", (quest_id,))
    if (await cur.fetchone())["n"] == 0:
        raise ApiError(409, "no_subgoals", "Add at least one subgoal before activating.")
    await db.get().execute("UPDATE quests SET state = 'active', version = version + 1, updated_at = ? WHERE id = ?",
                           (now_iso(), quest_id))
    await db.get().execute(
        "UPDATE profiles SET onboarding_step = 'done', updated_at = ? WHERE id = ? AND onboarding_step != 'done'",
        (now_iso(), profile_id))
    await db.get().commit()
    await events.publish("profile", profile_id, "quest.updated", quest_id, {"state": "active"})
    return await quest_with_subgoals(profile_id, quest_id)


async def archive_quest(profile_id: str, quest_id: str) -> dict:
    await quest_row(profile_id, quest_id)
    await db.get().execute("UPDATE quests SET state = 'archived', version = version + 1, updated_at = ? WHERE id = ?",
                           (now_iso(), quest_id))
    await db.get().commit()
    await events.publish("profile", profile_id, "quest.updated", quest_id, {"state": "archived"})
    return await quest_with_subgoals(profile_id, quest_id)


async def maybe_complete_quest(profile_id: str, quest_id: str) -> None:
    cur = await db.get().execute(
        "SELECT COUNT(*) AS total, SUM(CASE WHEN state='completed' THEN 1 ELSE 0 END) AS done"
        " FROM subgoals WHERE quest_id = ?", (quest_id,))
    row = await cur.fetchone()
    if row["total"] > 0 and row["done"] == row["total"]:
        await db.get().execute(
            "UPDATE quests SET state = 'completed', version = version + 1, updated_at = ? WHERE id = ? AND state = 'active'",
            (now_iso(), quest_id))
        await db.get().commit()
        await events.publish("profile", profile_id, "quest.updated", quest_id, {"state": "completed"})
