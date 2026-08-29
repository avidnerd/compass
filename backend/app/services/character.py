"""Companion: creation, care, needs drift, memories, reactions, evolution.

Humane rules enforced here: the companion never dies or gets sick, absence
never drops mood below 30, needs drift toward neutral rather than punishing.
"""
import json
import logging
from datetime import date

from .. import db, events, llm, openrouter
from ..errors import ApiError, not_found
from ..util import new_id, now, now_iso, parse_iso

logger = logging.getLogger("compass.character")

CARE_ACTIONS = {"feed", "play", "rest", "decorate", "encourage"}

_ENUM_FIELDS = {
    "species": llm.ALLOWED_SPECIES, "palette": llm.ALLOWED_PALETTES, "eyes": llm.ALLOWED_EYES,
    "markings": llm.ALLOWED_MARKINGS, "accessory": llm.ALLOWED_ACCESSORIES,
    "aura": llm.ALLOWED_AURAS, "habitat": llm.ALLOWED_HABITATS,
    "personality": llm.ALLOWED_PERSONALITIES, "voice_tone": llm.ALLOWED_TONES,
}


def _validate_enums(fields: dict) -> None:
    for key, allowed in _ENUM_FIELDS.items():
        if key in fields and fields[key] not in allowed:
            raise ApiError(422, "invalid_request", f"Invalid {key}: {fields[key]}")


def public_character(row: dict) -> dict:
    d = dict(row)
    d["props"] = json.loads(d.pop("props_json") or "[]")
    d["unlocks"] = json.loads(d.pop("unlocks_json") or "[]")
    d.pop("needs_updated_at", None)
    d.pop("last_play_bond_date", None)
    d.pop("last_coop_collab_date", None)
    return d


async def get_character(profile_id: str, apply_drift: bool = True) -> dict:
    cur = await db.get().execute("SELECT * FROM characters WHERE profile_id = ?", (profile_id,))
    row = await cur.fetchone()
    if row is None:
        raise not_found("character")
    ch = dict(row)
    if apply_drift:
        ch = await _drift_needs(ch)
    return ch


async def _drift_needs(ch: dict) -> dict:
    """Drift energy/mood toward neutral (65) at ~1 point/hour. Mood never
    drops below 30 from absence alone."""
    ref = ch.get("needs_updated_at") or ch["updated_at"]
    hours = max(0.0, (now() - parse_iso(ref)).total_seconds() / 3600)
    if hours < 1:
        return ch
    steps = int(hours)

    def toward(value: int, target: int, steps: int, floor: int | None = None) -> int:
        if value > target:
            value = max(target, value - steps)
        elif value < target:
            value = min(target, value + steps)
        if floor is not None:
            value = max(floor, value)
        return value

    energy = toward(ch["energy"], 65, steps)
    mood = toward(ch["mood"], 65, steps, floor=30)
    await db.get().execute(
        "UPDATE characters SET energy = ?, mood = ?, needs_updated_at = ? WHERE profile_id = ?",
        (energy, mood, now_iso(), ch["profile_id"]))
    await db.get().commit()
    ch.update(energy=energy, mood=mood, needs_updated_at=now_iso())
    return ch


async def finalize_companion(profile_id: str, selection: dict) -> dict:
    cur = await db.get().execute("SELECT 1 FROM characters WHERE profile_id = ?", (profile_id,))
    if await cur.fetchone():
        raise ApiError(409, "character_exists", "This profile already has a companion.")
    fields = {
        "name": (selection.get("name") or "Pip")[:40],
        "pronouns": (selection.get("pronouns") or "they/them")[:20],
        "species": selection.get("species") or "sproutling",
        "palette": selection.get("palette") or "meadow",
        "eyes": selection.get("eyes") or "round",
        "markings": selection.get("markings") or "none",
        "accessory": selection.get("accessory") or "none",
        "aura": selection.get("aura") or "none",
        "habitat": selection.get("habitat") or "meadow",
        "personality": selection.get("personality") or "cheerful",
        "voice_tone": selection.get("voice_tone") or "warm",
    }
    _validate_enums(fields)
    props = [p for p in (selection.get("props") or []) if p in llm.ALLOWED_PROPS][:3]
    ts = now_iso()
    await db.get().execute(
        """INSERT INTO characters (profile_id, name, pronouns, species, palette, eyes, markings,
             accessory, aura, habitat, personality, voice_tone, props_json, needs_updated_at,
             created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (profile_id, *fields.values(), json.dumps(props), ts, ts, ts))
    await db.get().execute(
        "UPDATE profiles SET onboarding_step = 'quest', updated_at = ? WHERE id = ? AND onboarding_step IN ('connect','scan','companion')",
        (ts, profile_id))
    await db.get().commit()
    ch = await get_character(profile_id, apply_drift=False)
    await events.publish("profile", profile_id, "character.updated", profile_id,
                         {"reason": "created"})
    return ch


async def update_character(profile_id: str, patch: dict) -> dict:
    ch = await get_character(profile_id, apply_drift=False)
    allowed = {"name", "pronouns", "species", "palette", "eyes", "markings", "accessory",
               "aura", "habitat", "personality", "voice_tone", "expression", "animation"}
    fields = {k: v for k, v in patch.items() if k in allowed and v is not None}
    _validate_enums(fields)
    if "props" in patch and isinstance(patch["props"], list):
        fields["props_json"] = json.dumps([p for p in patch["props"] if p in llm.ALLOWED_PROPS][:4])
    if "evolve" in patch and patch["evolve"] in ("formA", "formB"):
        # Evolution: purely cosmetic, both forms stay available as unlocks.
        stage = sum(1 for lv in rewards_evolution_levels() if ch["level"] >= lv)
        if stage > ch["evolution_stage"]:
            fields["evolution_stage"] = stage
            unlocks = json.loads(ch["unlocks_json"] or "[]")
            new_unlocks = [f"aura:{llm.ALLOWED_AURAS[min(stage, len(llm.ALLOWED_AURAS)-1)]}",
                           f"accessory:{llm.ALLOWED_ACCESSORIES[min(stage + 3, len(llm.ALLOWED_ACCESSORIES)-1)]}"]
            fields["unlocks_json"] = json.dumps(sorted(set(unlocks + new_unlocks)))
    if fields:
        cols = ", ".join(f"{k} = ?" for k in fields)
        await db.get().execute(
            f"UPDATE characters SET {cols}, updated_at = ?, version = version + 1 WHERE profile_id = ?",
            (*fields.values(), now_iso(), profile_id))
        await db.get().commit()
        await events.publish("profile", profile_id, "character.updated", profile_id, {"reason": "edited"})
    return await get_character(profile_id, apply_drift=False)


def rewards_evolution_levels() -> list[int]:
    from . import rewards
    return rewards.EVOLUTION_LEVELS


async def care_action(profile_id: str, action: str, note: str | None = None,
                      cosmetic: str | None = None) -> dict:
    if action not in CARE_ACTIONS:
        raise ApiError(422, "invalid_request", f"Unknown care action: {action}")
    ch = await get_character(profile_id)
    updates: dict = {}
    message = ""
    today = date.today().isoformat()

    if action == "feed":
        if ch["care_points"] < 1:
            raise ApiError(409, "not_enough_care_points", "No care points left — finish a focus session to earn more.")
        updates = {"care_points": ch["care_points"] - 1, "energy": min(100, ch["energy"] + 15),
                   "expression": "happy", "animation": "munch"}
        message = "Nom nom! Energy +15."
    elif action == "play":
        if ch["care_points"] < 1:
            raise ApiError(409, "not_enough_care_points", "No care points left — finish a focus session to earn more.")
        bond_gain = 1 if ch.get("last_play_bond_date") != today else 0
        updates = {"care_points": ch["care_points"] - 1, "mood": min(100, ch["mood"] + 12),
                   "bond": min(100, ch["bond"] + bond_gain), "last_play_bond_date": today,
                   "expression": "joyful", "animation": "bounce"}
        message = "So fun! Mood +12" + (" and Bond +1." if bond_gain else ".")
    elif action == "rest":
        updates = {"energy": min(100, ch["energy"] + 5), "expression": "sleepy", "animation": "rest"}
        message = "Resting cozily. Energy recovers gradually."
    elif action == "decorate":
        unlocks = json.loads(ch["unlocks_json"] or "[]")
        if not cosmetic:
            raise ApiError(422, "invalid_request", "Pick a cosmetic to decorate with.")
        kind, _, value = cosmetic.partition(":")
        if cosmetic not in unlocks and value not in (llm.ALLOWED_PROPS):
            raise ApiError(409, "cosmetic_locked", "That cosmetic isn't unlocked yet.")
        if kind == "prop" or value in llm.ALLOWED_PROPS:
            props = json.loads(ch["props_json"] or "[]")
            name = value or cosmetic
            if name not in props:
                props = (props + [name])[-4:]
            updates = {"props_json": json.dumps(props)}
        elif kind in ("aura", "accessory") and value:
            updates = {kind: value}
        message = "The habitat looks lovely."
    elif action == "encourage":
        if not note or not note.strip():
            raise ApiError(422, "invalid_request", "Write a short note to remember.")
        await record_memory(profile_id, kind="encourage", text=note.strip()[:240])
        updates = {"mood": min(100, ch["mood"] + 3), "bond": min(100, ch["bond"] + 1),
                   "expression": "moved", "animation": "heart"}
        message = "Saved to the journal. Your companion holds it close."

    if updates:
        cols = ", ".join(f"{k} = ?" for k in updates)
        await db.get().execute(
            f"UPDATE characters SET {cols}, needs_updated_at = ?, updated_at = ?, version = version + 1 WHERE profile_id = ?",
            (*updates.values(), now_iso(), now_iso(), profile_id))
        await db.get().commit()
    await events.publish("profile", profile_id, "character.updated", profile_id, {"reason": action})
    ch = await get_character(profile_id, apply_drift=False)
    return {"character": public_character(ch), "message": message}


async def record_memory(profile_id: str, kind: str, text: str, visibility: str = "private") -> dict:
    memory_id = new_id()
    ts = now_iso()
    await db.get().execute(
        "INSERT INTO character_memories (id, profile_id, kind, text, visibility, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (memory_id, profile_id, kind, text[:300], visibility, ts, ts))
    await db.get().commit()
    return {"id": memory_id, "kind": kind, "text": text[:300], "visibility": visibility, "created_at": ts}


async def list_memories(profile_id: str, limit: int = 50, cursor: str | None = None) -> list[dict]:
    sql = "SELECT * FROM character_memories WHERE profile_id = ?"
    params: list = [profile_id]
    if cursor:
        sql += " AND created_at < ?"
        params.append(cursor)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(min(limit, 100))
    cur = await db.get().execute(sql, params)
    return [dict(r) for r in await cur.fetchall()]


async def react(profile_id: str, kind: str, outcome: str, category: str = "general",
                rewards_summary: dict | None = None) -> dict:
    """Generate (or template) a three-line companion reaction and persist the
    journal line. Only safe, high-level inputs ever reach the LLM."""
    try:
        ch = await get_character(profile_id, apply_drift=False)
    except ApiError:
        return {}
    persona = {"name": ch["name"], "personality": ch["personality"],
               "voice_tone": ch["voice_tone"], "pronouns": ch["pronouns"]}
    recent = await list_memories(profile_id, limit=3)
    event = {"kind": kind, "outcome": outcome, "category": category,
             "rewards": rewards_summary or {}, "memories": [m["text"][:80] for m in recent]}
    try:
        batch, _model = await llm.generate_reaction(profile_id, persona, event)
    except (openrouter.FreeModelUnavailable, openrouter.LLMOutputInvalid, Exception) as exc:
        if not isinstance(exc, (openrouter.FreeModelUnavailable, openrouter.LLMOutputInvalid)):
            logger.warning("[character] reaction generation failed: %s", type(exc).__name__)
        batch = llm.fallback_reaction(persona, event)
    await record_memory(profile_id, kind="reflection", text=batch.journal_memory)
    expression = {"verified": "proud", "needs_confirmation": "curious",
                  "not_completed": "gentle", "session_missed": "warm"}.get(outcome, "content")
    await db.get().execute(
        "UPDATE characters SET expression = ?, updated_at = ? WHERE profile_id = ?",
        (expression, now_iso(), profile_id))
    await db.get().commit()
    payload = {"reaction": batch.reaction, "encouragement": batch.encouragement,
               "journal_memory": batch.journal_memory, "outcome": outcome}
    await events.publish("profile", profile_id, "reaction.created", profile_id, payload)
    return payload


async def unlocks(profile_id: str) -> dict:
    ch = await get_character(profile_id, apply_drift=False)
    stage = ch["evolution_stage"]
    next_levels = [lv for lv in rewards_evolution_levels() if ch["level"] < lv]
    stats = {k: ch[v] for k, v in
             {"focus": "stat_focus", "curiosity": "stat_curiosity", "craft": "stat_craft",
              "communication": "stat_communication", "collaboration": "stat_collaboration",
              "balance": "stat_balance"}.items()}
    dominant = max(stats, key=stats.get)
    reached = sum(1 for lv in rewards_evolution_levels() if ch["level"] >= lv)
    return {
        "unlocks": json.loads(ch["unlocks_json"] or "[]"),
        "evolution_stage": stage,
        "evolution_available": reached > stage,
        "next_evolution_level": next_levels[0] if next_levels else None,
        "dominant_stat": dominant,
        "forms": [
            {"id": "formA", "label": f"Radiant {dominant.capitalize()} form", "aura": "soft-glow"},
            {"id": "formB", "label": f"Wild {dominant.capitalize()} form", "aura": "sparkles"},
        ] if reached > stage else [],
    }
