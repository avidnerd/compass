"""Deterministic scoring, XP, levels, stats. No LLM involvement, ever."""
import json
import math

from .. import db
from ..util import new_id, now_iso

STAT_COLUMNS = {
    "focus": "stat_focus", "curiosity": "stat_curiosity", "craft": "stat_craft",
    "communication": "stat_communication", "collaboration": "stat_collaboration",
    "balance": "stat_balance",
}

# Evidence source -> primary stat.
EVIDENCE_STAT = {
    "google_docs": "curiosity", "google_drive": "curiosity", "google_sheets": "craft",
    "google_slides": "craft", "github": "craft", "gmail": "communication",
    "google_meet": "communication", "google_calendar": "focus",
}

EVOLUTION_LEVELS = [3, 7, 12]


def level_threshold(level: int) -> int:
    """Cumulative XP required to REACH `level + 1` from the start."""
    return 25 * level * (level + 1)


def level_for_xp(xp: int) -> int:
    level = 1
    while xp >= level_threshold(level):
        level += 1
    return level


def continuity(paused_seconds: int, total_seconds: int) -> float:
    if total_seconds <= 0:
        return 1.0
    return max(0.0, 1 - paused_seconds / total_seconds)


def improvement_percentile(pre_score: float, prior_scores: list[float]) -> float:
    """Percentile of this session against the user's own recent baseline.
    Neutral 0.5 until five prior eligible sessions exist."""
    prior = prior_scores[:14]
    if len(prior) < 5:
        return 0.5
    below = sum(1 for s in prior if s < pre_score)
    equal = sum(1 for s in prior if s == pre_score)
    return (below + 0.5 * equal) / len(prior)


def calculate_focus_score(active_seconds: int, planned_seconds: int, paused_seconds: int,
                          total_seconds: int, completion: float,
                          prior_scores: list[float]) -> int:
    commitment = min(active_seconds / planned_seconds, 1.0) if planned_seconds > 0 else 0.0
    cont = continuity(paused_seconds, total_seconds)
    # Pre-improvement score on a 0-100 scale, used only to rank against the
    # user's own prior sessions.
    pre = 100 * (0.30 * commitment + 0.45 * completion + 0.15 * cont) / 0.90
    improvement = improvement_percentile(pre, prior_scores)
    score = round(100 * (0.30 * commitment + 0.45 * completion + 0.15 * cont + 0.10 * improvement))
    return max(0, min(100, score))


def session_rewards(focus_score: int, primary_stat: str | None, human_confirmed: bool) -> dict:
    xp = 10 + math.floor(focus_score / 5)
    care = 1 + math.floor(focus_score / 25)
    if human_confirmed:
        xp = round(xp * 0.8)
        care = max(1, round(care * 0.8))
    focus_gain = 2 if focus_score >= 85 else (1 if focus_score >= 60 else 0)
    if human_confirmed:
        focus_gain = min(focus_gain, 1)
    stats: dict[str, int] = {}
    if focus_gain:
        stats["focus"] = focus_gain
        if primary_stat and primary_stat != "focus":
            stats[primary_stat] = focus_gain
    return {"xp": xp, "care_points": care, "stats": stats}


def primary_stat_for_evidence(evidence: list[dict]) -> str | None:
    counts: dict[str, int] = {}
    for item in evidence:
        stat = EVIDENCE_STAT.get(item.get("source") or "")
        if stat:
            counts[stat] = counts.get(stat, 0) + 1
    if not counts:
        return None
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


async def prior_focus_scores(profile_id: str, before_session_id: str) -> list[float]:
    cur = await db.get().execute(
        """SELECT focus_score FROM focus_sessions
           WHERE profile_id = ? AND id != ? AND state = 'completed' AND focus_score IS NOT NULL
           ORDER BY created_at DESC LIMIT 14""",
        (profile_id, before_session_id))
    return [r["focus_score"] for r in await cur.fetchall()]


async def apply_rewards(profile_id: str, source_event_key: str, xp: int, care_points: int,
                        stats: dict[str, int], reason: str) -> dict | None:
    """Append-only, idempotent by source_event_key. Returns the applied
    changes (with level-up info) or None if this key was already granted."""
    conn = db.get()
    try:
        await conn.execute(
            "INSERT INTO stat_ledger (id, profile_id, source_event_key, xp, care_points, stats_json, reason, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (new_id(), profile_id, source_event_key, xp, care_points, json.dumps(stats), reason, now_iso()))
    except Exception:
        await conn.rollback()
        return None  # duplicate source event: rewards already granted

    cur = await conn.execute("SELECT * FROM characters WHERE profile_id = ?", (profile_id,))
    ch = await cur.fetchone()
    result = {"xp": xp, "care_points": care_points, "stats": stats,
              "leveled_up": False, "level": None, "evolution_available": False}
    if ch is not None:
        old_level = ch["level"]
        new_xp = ch["xp"] + xp
        new_level = level_for_xp(new_xp)
        updates = {"xp": new_xp, "level": new_level, "care_points": ch["care_points"] + care_points}
        for stat, gain in stats.items():
            col = STAT_COLUMNS[stat]
            updates[col] = min(100, ch[col] + gain)
        stage = sum(1 for lv in EVOLUTION_LEVELS if new_level >= lv)
        evolution_available = stage > ch["evolution_stage"]
        cols = ", ".join(f"{k} = ?" for k in updates)
        await conn.execute(
            f"UPDATE characters SET {cols}, updated_at = ?, version = version + 1 WHERE profile_id = ?",
            (*updates.values(), now_iso(), profile_id))
        result.update({"leveled_up": new_level > old_level, "level": new_level,
                       "evolution_available": evolution_available})
    await conn.commit()
    return result


def battle_power(focus_score: int, verification_result: str, human_confirmed: bool,
                 relevant_stat_value: int) -> int:
    power = 0.75 * focus_score
    if verification_result == "verified" and not human_confirmed:
        power += 15
    elif verification_result == "verified" and human_confirmed:
        power += 8
    power += min(10, relevant_stat_value / 10)
    return min(100, round(power))


def boss_damage(focus_score: int, character_level: int, human_confirmed: bool) -> int:
    damage = 20 + 0.60 * focus_score + 2 * min(character_level, 10)
    if human_confirmed:
        damage *= 0.8
    return round(damage)
