"""Focus rooms: shared presence and preset reactions.

A room shares readiness and a timer. It never shares goals, filenames or
evidence — see PRODUCT.md, "Privacy survives multiplayer"."""
import logging

from .. import db, events
from ..errors import ApiError, forbidden, not_found
from ..util import new_id, new_room_code, now_iso

logger = logging.getLogger("compass.parties")

MAX_MEMBERS = 6
ALLOWED_THEMES = ["aurora", "ember", "tidepool", "meadow", "midnight"]
ALLOWED_EMOTES = ["cheer", "heart", "spark", "flex", "tea", "confetti"]


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
            member.update({"is_simulated": False, "avatar": "compass", "status": "online"})
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
    return {"id": p["id"], "code": p["code"], "name": p["name"], "theme": p["theme"],
            "owner_profile_id": p["owner_profile_id"], "members": members, "created_at": p["created_at"]}


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
