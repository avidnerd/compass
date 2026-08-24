"""Parties, preset emotes, and co-op boss encounters."""
import json
import logging
from datetime import date, timedelta

from .. import db, events, jobs, llm, openrouter
from ..errors import ApiError, forbidden, not_found
from ..util import new_id, new_room_code, now, now_iso, parse_iso
from . import rewards

logger = logging.getLogger("compass.parties")

MAX_MEMBERS = 6
ALLOWED_THEMES = ["aurora", "ember", "tidepool", "meadow", "midnight"]
ALLOWED_EMOTES = ["cheer", "heart", "spark", "flex", "tea", "confetti"]
DIFFICULTY_MULTIPLIER = {"easy": 1.0, "standard": 1.5, "epic": 2.0}
BOSS_HOURS = 24


async def party_row(party_id: str) -> dict:
    cur = await db.get().execute("SELECT * FROM parties WHERE id = ?", (party_id,))
    row = await cur.fetchone()
    if row is None:
        raise not_found("party")
    return dict(row)


async def _members(party_id: str) -> list[dict]:
    from . import demo_multiplayer
    cur = await db.get().execute(
        """SELECT m.profile_id, m.joined_at, p.display_name FROM party_members m
           JOIN profiles p ON p.id = m.profile_id WHERE m.party_id = ? ORDER BY m.joined_at""",
        (party_id,))
    members = []
    for row in await cur.fetchall():
        member = dict(row)
        if demo_multiplayer.is_simulated(member["profile_id"]):
            player = demo_multiplayer.get_player(member["profile_id"])
            member.update({
                "is_simulated": True, "avatar": player["avatar"], "status": player["status"],
                "title": player["title"], "companion_name": player["companion_name"],
            })
        else:
            member.update({"is_simulated": False, "avatar": "🧭", "status": "online"})
        members.append(member)
    return members


async def _require_member(party_id: str, profile_id: str) -> None:
    cur = await db.get().execute(
        "SELECT 1 FROM party_members WHERE party_id = ? AND profile_id = ?", (party_id, profile_id))
    if await cur.fetchone() is None:
        raise forbidden("You are not in this party.")


async def public_party(party_id: str) -> dict:
    p = await party_row(party_id)
    members = await _members(party_id)
    boss = await active_boss(party_id)
    return {"id": p["id"], "code": p["code"], "name": p["name"], "theme": p["theme"],
            "owner_profile_id": p["owner_profile_id"], "members": members,
            "active_boss": boss, "created_at": p["created_at"]}


async def create_party(profile: dict, name: str, theme: str | None,
                       simulated_player_ids: list[str] | None = None) -> dict:
    from . import demo_multiplayer
    simulated_ids = demo_multiplayer.validate_player_ids(simulated_player_ids or [], limit=5)
    await demo_multiplayer.ensure_profiles(simulated_ids)
    party_id = new_id()
    ts = now_iso()
    await db.get().execute(
        "INSERT INTO parties (id, code, name, theme, owner_profile_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (party_id, new_room_code(), (name or "Adventuring Party")[:60],
         theme if theme in ALLOWED_THEMES else "aurora", profile["id"], ts))
    await db.get().execute(
        "INSERT INTO party_members (party_id, profile_id, joined_at) VALUES (?, ?, ?)",
        (party_id, profile["id"], ts))
    for simulated_id in simulated_ids:
        await db.get().execute(
            "INSERT INTO party_members (party_id, profile_id, joined_at) VALUES (?, ?, ?)",
            (party_id, simulated_id, ts))
    await db.get().commit()
    return await public_party(party_id)


async def join_party(profile: dict, code: str) -> dict:
    cur = await db.get().execute("SELECT * FROM parties WHERE code = ?", (code.strip().upper(),))
    row = await cur.fetchone()
    if row is None:
        raise not_found("party")
    party_id = row["id"]
    members = await _members(party_id)
    if any(m["profile_id"] == profile["id"] for m in members):
        return await public_party(party_id)
    if len(members) >= MAX_MEMBERS:
        raise ApiError(409, "party_full", "That party is full (max 6 members).")
    await db.get().execute(
        "INSERT INTO party_members (party_id, profile_id, joined_at) VALUES (?, ?, ?)",
        (party_id, profile["id"], now_iso()))
    await db.get().commit()
    await events.publish("party", party_id, "party.updated", party_id, {"reason": "member_joined"})
    return await public_party(party_id)


async def list_parties(profile_id: str) -> list[dict]:
    cur = await db.get().execute(
        "SELECT party_id FROM party_members WHERE profile_id = ?", (profile_id,))
    return [await public_party(r["party_id"]) for r in await cur.fetchall()]


async def patch_party(profile: dict, party_id: str, patch: dict) -> dict:
    p = await party_row(party_id)
    if p["owner_profile_id"] != profile["id"]:
        raise forbidden("Only the party owner can edit it.")
    fields = {}
    if patch.get("name"):
        fields["name"] = str(patch["name"])[:60]
    if patch.get("theme") in ALLOWED_THEMES:
        fields["theme"] = patch["theme"]
    if fields:
        cols = ", ".join(f"{k} = ?" for k in fields)
        await db.get().execute(f"UPDATE parties SET {cols} WHERE id = ?", (*fields.values(), party_id))
        await db.get().commit()
        await events.publish("party", party_id, "party.updated", party_id, {"reason": "edited"})
    return await public_party(party_id)


async def leave_party(profile: dict, party_id: str) -> None:
    await _require_member(party_id, profile["id"])
    await db.get().execute("DELETE FROM party_members WHERE party_id = ? AND profile_id = ?",
                           (party_id, profile["id"]))
    await db.get().commit()
    await events.publish("party", party_id, "party.updated", party_id, {"reason": "member_left"})


async def send_emote(profile: dict, party_id: str, emote: str) -> None:
    await _require_member(party_id, profile["id"])
    if emote not in ALLOWED_EMOTES:
        raise ApiError(422, "invalid_request", "Unknown emote.")
    await events.publish("party", party_id, "party.emote", party_id,
                         {"profile_id": profile["id"], "display_name": profile["display_name"],
                          "emote": emote})


# ---------------------------------------------------------------- bosses

async def active_boss(party_id: str) -> dict | None:
    cur = await db.get().execute(
        "SELECT * FROM boss_encounters WHERE party_id = ? ORDER BY started_at DESC LIMIT 1", (party_id,))
    row = await cur.fetchone()
    if row is None:
        return None
    boss = dict(row)
    if boss["state"] == "active" and parse_iso(boss["expires_at"]) <= now():
        # Expiry carries no punishment; the encounter simply closes.
        await db.get().execute(
            "UPDATE boss_encounters SET state = 'expired', resolved_at = ? WHERE id = ?",
            (now_iso(), boss["id"]))
        await db.get().commit()
        boss["state"] = "expired"
    boss["theme"] = json.loads(boss.pop("theme_json") or "{}")
    cur = await db.get().execute(
        """SELECT c.profile_id, p.display_name, SUM(c.damage) AS damage, COUNT(*) AS sessions
           FROM boss_contributions c JOIN profiles p ON p.id = c.profile_id
           WHERE c.encounter_id = ? GROUP BY c.profile_id ORDER BY damage DESC""",
        (boss["id"],))
    boss["contributions"] = [dict(r) for r in await cur.fetchall()]
    return boss


async def start_boss_encounter(profile: dict, party_id: str, difficulty: str) -> dict:
    from . import demo_multiplayer
    await _require_member(party_id, profile["id"])
    if difficulty not in DIFFICULTY_MULTIPLIER:
        raise ApiError(422, "invalid_request", "Difficulty must be easy, standard, or epic.")
    boss = await active_boss(party_id)
    if boss and boss["state"] == "active":
        raise ApiError(409, "boss_active", "This party already has an active boss.")
    members = await _members(party_id)
    hp = round(100 * len(members) * DIFFICULTY_MULTIPLIER[difficulty])
    encounter_id = new_id()
    ts = now()
    theme = dict(llm.BUNDLED_BOSS_THEMES[hash(encounter_id) % len(llm.BUNDLED_BOSS_THEMES)])
    await db.get().execute(
        """INSERT INTO boss_encounters (id, party_id, difficulty, hp_max, hp_current, state,
             theme_json, started_at, expires_at)
           VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)""",
        (encounter_id, party_id, difficulty, hp, hp, json.dumps(theme), ts.isoformat(),
         (ts + timedelta(hours=BOSS_HOURS)).isoformat()))
    simulated_damage = 0
    for member in members:
        if not demo_multiplayer.is_simulated(member["profile_id"]):
            continue
        player = demo_multiplayer.get_player(member["profile_id"])
        damage = 16 + player["stats"]["collaboration"] // 4
        simulated_damage += damage
        await db.get().execute(
            """INSERT INTO boss_contributions
                 (id, encounter_id, profile_id, session_id, damage, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (new_id(), encounter_id, member["profile_id"],
             f"simulated:{encounter_id}:{member['profile_id']}", damage, now_iso()))
    if simulated_damage:
        await db.get().execute(
            "UPDATE boss_encounters SET hp_current = ? WHERE id = ?",
            (max(0, hp - simulated_damage), encounter_id))
    await db.get().commit()
    await jobs.enqueue("boss_theme", profile["id"], {"encounter_id": encounter_id,
                                                     "party_id": party_id})
    await events.publish("party", party_id, "boss.updated", encounter_id,
                         {"reason": "started", "hp_current": hp, "hp_max": hp})
    return await public_party(party_id)


@jobs.register("boss_theme")
async def run_boss_theme(job: dict) -> dict:
    """Flavor the boss with shared, non-sensitive interest tags (optional)."""
    encounter_id = job["payload"]["encounter_id"]
    party_id = job["payload"]["party_id"]
    cur = await db.get().execute("SELECT * FROM boss_encounters WHERE id = ?", (encounter_id,))
    row = await cur.fetchone()
    if row is None or row["state"] != "active":
        return {}
    # Overlapping interest labels across members, if any (labels only, no sources).
    members = await _members(party_id)
    label_sets = []
    for m in members:
        c2 = await db.get().execute("SELECT topics_json FROM interest_profiles WHERE profile_id = ?",
                                    (m["profile_id"],))
        r2 = await c2.fetchone()
        if r2:
            label_sets.append({t["label"].lower() for t in json.loads(r2["topics_json"])})
    shared = sorted(set.intersection(*label_sets)) if len(label_sets) >= 2 else []
    try:
        theme, _model = await llm.generate_boss_theme(job["profile_id"], shared[:5])
        await db.get().execute("UPDATE boss_encounters SET theme_json = ? WHERE id = ? AND state = 'active'",
                               (json.dumps(theme.model_dump()), encounter_id))
        await db.get().commit()
        await events.publish("party", party_id, "boss.updated", encounter_id, {"reason": "theme"})
    except (openrouter.FreeModelUnavailable, openrouter.LLMOutputInvalid):
        pass  # bundled theme stays
    return {"result_type": "boss_encounter", "result_id": encounter_id}


async def apply_boss_contribution(profile: dict, session: dict, completed: bool,
                                  human_confirmed: bool, focus_score: int) -> None:
    """One eligible contribution per focus session, to the newest active boss
    among the profile's parties. Deterministic damage."""
    if not completed:
        return
    cur = await db.get().execute(
        """SELECT b.* FROM boss_encounters b
           JOIN party_members m ON m.party_id = b.party_id
           WHERE m.profile_id = ? AND b.state = 'active'
           ORDER BY b.started_at DESC LIMIT 1""",
        (profile["id"],))
    row = await cur.fetchone()
    if row is None:
        return
    boss = dict(row)
    if parse_iso(boss["expires_at"]) <= now():
        return
    c2 = await db.get().execute("SELECT level FROM characters WHERE profile_id = ?", (profile["id"],))
    ch = await c2.fetchone()
    level = ch["level"] if ch else 1
    damage = rewards.boss_damage(focus_score, level, human_confirmed)
    try:
        await db.get().execute(
            "INSERT INTO boss_contributions (id, encounter_id, profile_id, session_id, damage, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (new_id(), boss["id"], profile["id"], session["id"], damage, now_iso()))
    except Exception:
        await db.get().rollback()
        return  # this session already contributed
    hp = max(0, boss["hp_current"] - damage)
    await db.get().execute("UPDATE boss_encounters SET hp_current = ? WHERE id = ?", (hp, boss["id"]))
    await db.get().commit()

    # +1 Collaboration at most once per day for eligible co-op contributions.
    today = date.today().isoformat()
    if ch is not None:
        c3 = await db.get().execute(
            "SELECT last_coop_collab_date FROM characters WHERE profile_id = ?", (profile["id"],))
        r3 = await c3.fetchone()
        if r3 and r3["last_coop_collab_date"] != today:
            await rewards.apply_rewards(profile["id"], f"coop:{profile['id']}:{today}",
                                        0, 0, {"collaboration": 1}, reason="Party contribution")
            await db.get().execute(
                "UPDATE characters SET last_coop_collab_date = ? WHERE profile_id = ?",
                (today, profile["id"]))
            await db.get().commit()

    await events.publish("party", boss["party_id"], "boss.updated", boss["id"],
                         {"reason": "damage", "damage": damage, "hp_current": hp,
                          "hp_max": boss["hp_max"], "by_display_name": profile["display_name"]})
    if hp == 0:
        await resolve_boss(boss["id"])


async def resolve_boss(encounter_id: str) -> None:
    cur = await db.get().execute("SELECT * FROM boss_encounters WHERE id = ?", (encounter_id,))
    row = await cur.fetchone()
    if row is None or row["state"] != "active":
        return
    boss = dict(row)
    await db.get().execute(
        "UPDATE boss_encounters SET state = 'defeated', resolved_at = ? WHERE id = ?",
        (now_iso(), encounter_id))
    await db.get().commit()
    theme = json.loads(boss["theme_json"] or "{}")
    await events.publish("party", boss["party_id"], "boss.defeated", encounter_id,
                         {"name": theme.get("name"), "defeat_line": theme.get("defeat_line")})

    # Local rewards: cosmetic + habitat prop + companion memory for contributors.
    from . import character as character_service
    cur = await db.get().execute(
        "SELECT DISTINCT profile_id FROM boss_contributions WHERE encounter_id = ?", (encounter_id,))
    for r in await cur.fetchall():
        pid = r["profile_id"]
        try:
            ch = await character_service.get_character(pid, apply_drift=False)
        except ApiError:
            continue
        unlocks = json.loads(ch["unlocks_json"] or "[]")
        for u in ("accessory:crown", "prop:trophy"):
            if u not in unlocks:
                unlocks.append(u)
        await db.get().execute(
            "UPDATE characters SET unlocks_json = ?, updated_at = ? WHERE profile_id = ?",
            (json.dumps(unlocks), now_iso(), pid))
        await db.get().commit()
        await character_service.record_memory(
            pid, kind="boss", text=f"We defeated {theme.get('name') or 'a mighty boss'} with our party!")
        await character_service.react(pid, "boss_defeated", "verified", "party")


async def contributions(profile_id: str, party_id: str) -> list[dict]:
    await _require_member(party_id, profile_id)
    cur = await db.get().execute(
        """SELECT c.encounter_id, c.profile_id, p.display_name, c.damage, c.created_at
           FROM boss_contributions c
           JOIN boss_encounters b ON b.id = c.encounter_id
           JOIN profiles p ON p.id = c.profile_id
           WHERE b.party_id = ? ORDER BY c.created_at DESC LIMIT 100""",
        (party_id,))
    return [dict(r) for r in await cur.fetchall()]


async def boss_encounter(profile_id: str, party_id: str, encounter_id: str) -> dict:
    await _require_member(party_id, profile_id)
    cur = await db.get().execute(
        "SELECT * FROM boss_encounters WHERE id = ? AND party_id = ?", (encounter_id, party_id))
    row = await cur.fetchone()
    if row is None:
        raise not_found("boss encounter")
    boss = dict(row)
    boss["theme"] = json.loads(boss.pop("theme_json") or "{}")
    cur = await db.get().execute(
        """SELECT c.profile_id, p.display_name, SUM(c.damage) AS damage, COUNT(*) AS sessions
           FROM boss_contributions c JOIN profiles p ON p.id = c.profile_id
           WHERE c.encounter_id = ? GROUP BY c.profile_id ORDER BY damage DESC""",
        (encounter_id,))
    boss["contributions"] = [dict(r) for r in await cur.fetchall()]
    return boss
