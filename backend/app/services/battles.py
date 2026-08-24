"""Synchronized focus battles. Room payloads never contain goals, subgoal
titles, filenames, or evidence — only timers, readiness, generic momentum,
placements, and display names."""
import asyncio
import json
import logging
from datetime import timedelta

from .. import db, events
from ..errors import ApiError, forbidden, not_found
from ..util import new_id, new_room_code, now, now_iso, parse_iso
from . import rewards

logger = logging.getLogger("compass.battles")

ALLOWED_MINUTES = {15, 25, 50}
COUNTDOWN_SECONDS = 5
MAX_PLAYERS = 4

_timers: dict[str, asyncio.Task] = {}


async def battle_row(battle_id: str) -> dict:
    cur = await db.get().execute("SELECT * FROM battles WHERE id = ?", (battle_id,))
    row = await cur.fetchone()
    if row is None:
        raise not_found("battle")
    return dict(row)


async def _players(battle_id: str) -> list[dict]:
    cur = await db.get().execute(
        "SELECT * FROM battle_players WHERE battle_id = ? ORDER BY joined_at", (battle_id,))
    return [dict(r) for r in await cur.fetchall()]


async def public_battle(battle_id: str, viewer_profile_id: str | None = None) -> dict:
    """Safe room payload. A player's own subgoal/session ids are included only
    for the viewer themself."""
    from . import demo_multiplayer
    b = await battle_row(battle_id)
    players = await _players(battle_id)
    out_players = []
    for p in players:
        entry = {
            "profile_id": p["profile_id"], "display_name": p["display_name"],
            "ready": bool(p["ready"]), "left": p["left_at"] is not None,
            "has_subgoal": p["subgoal_id"] is not None,
            "placement": p["placement"],
            "power": p["power"] if b["state"] in ("resolving", "completed") else None,
        }
        if demo_multiplayer.is_simulated(p["profile_id"]):
            simulated = demo_multiplayer.get_player(p["profile_id"])
            entry.update({"is_simulated": True, "avatar": simulated["avatar"],
                          "title": simulated["title"], "status": simulated["status"]})
        else:
            entry.update({"is_simulated": False, "avatar": "🧭", "status": "online"})
        if viewer_profile_id and p["profile_id"] == viewer_profile_id:
            entry["subgoal_id"] = p["subgoal_id"]
            entry["session_id"] = p["session_id"]
        out_players.append(entry)
    return {
        "id": b["id"], "code": b["code"], "host_profile_id": b["host_profile_id"],
        "duration_seconds": b["duration_seconds"], "state": b["state"],
        "countdown_at": b["countdown_at"], "started_at": b["started_at"], "ends_at": b["ends_at"],
        "server_time": now_iso(), "players": out_players,
    }


async def _require_player(battle_id: str, profile_id: str) -> dict:
    cur = await db.get().execute(
        "SELECT * FROM battle_players WHERE battle_id = ? AND profile_id = ?",
        (battle_id, profile_id))
    row = await cur.fetchone()
    if row is None:
        raise forbidden("You are not in this battle.")
    return dict(row)


async def create_battle(profile: dict, minutes: int, demo: bool = False,
                        opponent_ids: list[str] | None = None) -> dict:
    from . import demo_multiplayer
    from ..config import settings
    if demo or (settings.demo_mode and minutes == 1):
        duration = 60
    elif minutes in ALLOWED_MINUTES:
        duration = minutes * 60
    else:
        raise ApiError(422, "invalid_request", "Battle length must be 15, 25, or 50 minutes (or 1 in demo mode).")
    simulated_ids = demo_multiplayer.validate_player_ids(opponent_ids or [], limit=3)
    await demo_multiplayer.ensure_profiles(simulated_ids)
    battle_id = new_id()
    ts = now_iso()
    code = new_room_code()
    await db.get().execute(
        "INSERT INTO battles (id, code, host_profile_id, duration_seconds, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?)", (battle_id, code, profile["id"], duration, ts, ts))
    await db.get().execute(
        "INSERT INTO battle_players (battle_id, profile_id, display_name, joined_at) VALUES (?, ?, ?, ?)",
        (battle_id, profile["id"], profile["display_name"], ts))
    for opponent_id in simulated_ids:
        opponent = demo_multiplayer.get_player(opponent_id)
        await db.get().execute(
            """INSERT INTO battle_players
                 (battle_id, profile_id, display_name, ready, power, joined_at)
               VALUES (?, ?, ?, 1, ?, ?)""",
            (battle_id, opponent_id, opponent["display_name"], opponent["battle_power"], ts))
    await db.get().commit()
    return await public_battle(battle_id, profile["id"])


async def join_battle(profile: dict, code: str) -> dict:
    cur = await db.get().execute("SELECT * FROM battles WHERE code = ?", (code.strip().upper(),))
    row = await cur.fetchone()
    if row is None:
        raise not_found("battle")
    b = dict(row)
    if b["state"] != "waiting":
        raise ApiError(409, "battle_started", "That battle has already started.")
    players = await _players(b["id"])
    if any(p["profile_id"] == profile["id"] for p in players):
        return await public_battle(b["id"], profile["id"])
    if len([p for p in players if p["left_at"] is None]) >= MAX_PLAYERS:
        raise ApiError(409, "battle_full", "That battle is full (max 4 players).")
    await db.get().execute(
        "INSERT INTO battle_players (battle_id, profile_id, display_name, joined_at) VALUES (?, ?, ?, ?)",
        (b["id"], profile["id"], profile["display_name"], now_iso()))
    await db.get().commit()
    await events.publish("battle", b["id"], "battle.updated", b["id"], {"reason": "player_joined"})
    return await public_battle(b["id"], profile["id"])


async def set_ready(profile: dict, battle_id: str, ready: bool, subgoal_id: str | None) -> dict:
    b = await battle_row(battle_id)
    if b["state"] != "waiting":
        raise ApiError(409, "invalid_state", "The battle is no longer accepting readiness changes.")
    await _require_player(battle_id, profile["id"])
    if subgoal_id:
        cur = await db.get().execute("SELECT profile_id FROM subgoals WHERE id = ?", (subgoal_id,))
        row = await cur.fetchone()
        if row is None or row["profile_id"] != profile["id"]:
            raise forbidden("That subgoal is not yours.")
    await db.get().execute(
        "UPDATE battle_players SET ready = ?, subgoal_id = COALESCE(?, subgoal_id) WHERE battle_id = ? AND profile_id = ?",
        (1 if ready else 0, subgoal_id, battle_id, profile["id"]))
    await db.get().commit()
    await events.publish("battle", battle_id, "battle.updated", battle_id, {"reason": "ready_changed"})
    return await public_battle(battle_id, profile["id"])


async def start_battle(profile: dict, battle_id: str) -> dict:
    b = await battle_row(battle_id)
    if b["host_profile_id"] != profile["id"]:
        raise forbidden("Only the host can start the battle.")
    if b["state"] != "waiting":
        raise ApiError(409, "invalid_state", "The battle already started.")
    players = [p for p in await _players(battle_id) if p["left_at"] is None]
    if len(players) < 2:
        raise ApiError(409, "not_enough_players", "Battles need at least two players.")
    if not all(p["ready"] for p in players):
        raise ApiError(409, "players_not_ready", "Everyone must be ready first.")
    await db.get().execute(
        "UPDATE battles SET state = 'countdown', countdown_at = ?, updated_at = ? WHERE id = ?",
        (now_iso(), now_iso(), battle_id))
    await db.get().commit()
    await events.publish("battle", battle_id, "battle.countdown", battle_id,
                         {"seconds": COUNTDOWN_SECONDS})
    _timers[battle_id] = asyncio.create_task(_countdown_then_start(battle_id))
    return await public_battle(battle_id, profile["id"])


async def _countdown_then_start(battle_id: str) -> None:
    try:
        await asyncio.sleep(COUNTDOWN_SECONDS)
        await _activate(battle_id)
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("[battles] countdown failed for %s", battle_id[:8])


async def _activate(battle_id: str) -> None:
    from . import demo_multiplayer, focus, profiles as profile_service
    b = await battle_row(battle_id)
    if b["state"] != "countdown":
        return
    # Every player's focus session is created BEFORE the battle flips to active.
    # A client that sees state == "active" must be able to rely on session_id
    # being there; doing it the other way round exposes a window where the room
    # looks live but nobody has a session yet.
    for p in [p for p in await _players(battle_id) if p["left_at"] is None]:
        if demo_multiplayer.is_simulated(p["profile_id"]):
            continue
        profile = await profile_service.get_profile(p["profile_id"])
        try:
            session = await focus.start_focus_session(
                profile,
                {"subgoal_id": p["subgoal_id"], "planned_minutes": max(1, b["duration_seconds"] // 60),
                 "demo": b["duration_seconds"] <= 60},
                battle_id=battle_id)
            await db.get().execute(
                "UPDATE battle_players SET session_id = ? WHERE battle_id = ? AND profile_id = ?",
                (session["id"], battle_id, p["profile_id"]))
            await db.get().commit()
        except ApiError as exc:
            logger.warning("[battles] could not start session for player: %s", exc.code)

    started = now()
    ends = started + timedelta(seconds=b["duration_seconds"])
    await db.get().execute(
        "UPDATE battles SET state = 'active', started_at = ?, ends_at = ?, updated_at = ? WHERE id = ?",
        (started.isoformat(), ends.isoformat(), now_iso(), battle_id))
    await db.get().commit()
    await events.publish("battle", battle_id, "battle.updated", battle_id, {"reason": "started"})
    _timers[battle_id] = asyncio.create_task(_auto_finish(battle_id, b["duration_seconds"]))


async def _auto_finish(battle_id: str, delay_seconds: float) -> None:
    try:
        await asyncio.sleep(max(0, delay_seconds))
        from . import focus
        b = await battle_row(battle_id)
        if b["state"] != "active":
            return
        await db.get().execute("UPDATE battles SET state = 'resolving', updated_at = ? WHERE id = ?",
                               (now_iso(), battle_id))
        await db.get().commit()
        await events.publish("battle", battle_id, "battle.updated", battle_id, {"reason": "time_up"})
        for p in await _players(battle_id):
            if p["session_id"] and p["left_at"] is None:
                try:
                    await focus.finish_focus_session(p["profile_id"], p["session_id"])
                except ApiError:
                    pass
        await maybe_resolve(battle_id)
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("[battles] auto-finish failed for %s", battle_id[:8])


async def leave_battle(profile: dict, battle_id: str) -> dict:
    await _require_player(battle_id, profile["id"])
    await db.get().execute(
        "UPDATE battle_players SET left_at = ?, ready = 0 WHERE battle_id = ? AND profile_id = ?",
        (now_iso(), battle_id, profile["id"]))
    await db.get().commit()
    await events.publish("battle", battle_id, "battle.updated", battle_id, {"reason": "player_left"})
    await maybe_resolve(battle_id)
    return await public_battle(battle_id, profile["id"])


async def cancel_battle(profile: dict, battle_id: str) -> dict:
    b = await battle_row(battle_id)
    if b["host_profile_id"] != profile["id"]:
        raise forbidden("Only the host can cancel the battle.")
    if b["state"] in ("completed", "canceled"):
        return await public_battle(battle_id, profile["id"])
    await db.get().execute("UPDATE battles SET state = 'canceled', updated_at = ? WHERE id = ?",
                           (now_iso(), battle_id))
    await db.get().commit()
    task = _timers.pop(battle_id, None)
    if task:
        task.cancel()
    await events.publish("battle", battle_id, "battle.updated", battle_id, {"reason": "canceled"})
    return await public_battle(battle_id, profile["id"])


async def on_session_verified(profile: dict, session: dict, verification: dict,
                              focus_score: int, human_confirmed: bool) -> None:
    """Called by the focus pipeline when a battle-linked session completes."""
    battle_id = session["battle_id"]
    try:
        b = await battle_row(battle_id)
    except ApiError:
        return
    if b["state"] in ("completed", "canceled"):
        return  # placements are final; late confirmations don't reshuffle them
    cur = await db.get().execute("SELECT * FROM characters WHERE profile_id = ?", (profile["id"],))
    ch = await cur.fetchone()
    stat_value = 0
    if ch is not None:
        stat_value = max(ch["stat_focus"], ch["stat_craft"], ch["stat_curiosity"])
    power = rewards.battle_power(focus_score, verification["result"], human_confirmed, stat_value)
    await db.get().execute(
        "UPDATE battle_players SET power = ? WHERE battle_id = ? AND profile_id = ?",
        (power, battle_id, profile["id"]))
    await db.get().commit()
    if b["state"] == "active":
        # Generic momentum only — no scores are revealed during play.
        await events.publish("battle", battle_id, "battle.updated", battle_id,
                             {"reason": "momentum", "profile_id": profile["id"]})
    await maybe_resolve(battle_id)


async def _claim(battle_id: str, final_state: str) -> bool:
    """Move a battle out of play exactly once. True only for the caller that won."""
    cur = await db.get().execute(
        "UPDATE battles SET state = ?, updated_at = ? WHERE id = ? AND state IN ('active','resolving')",
        (final_state, now_iso(), battle_id))
    await db.get().commit()
    return cur.rowcount > 0


async def maybe_resolve(battle_id: str) -> None:
    from . import demo_multiplayer
    b = await battle_row(battle_id)
    if b["state"] not in ("active", "resolving"):
        return
    players = await _players(battle_id)
    active = [p for p in players if p["left_at"] is None]
    if not active:
        await _claim(battle_id, "canceled")
        return
    if any(p["power"] is None for p in active):
        return  # someone is still being verified

    # Placement with two-point draw window.
    ranked = sorted(active, key=lambda p: -(p["power"] or 0))
    placements: dict[str, int] = {}
    place = 1
    for i, p in enumerate(ranked):
        if i > 0 and (ranked[i - 1]["power"] or 0) - (p["power"] or 0) <= 2:
            placements[p["profile_id"]] = placements[ranked[i - 1]["profile_id"]]
        else:
            placements[p["profile_id"]] = place
        place = i + 2
    # Claim the battle before doing anything observable. maybe_resolve is called
    # from the auto-finish timer, from leave_battle, and from every player's
    # verification callback, so without an atomic claim two of them can both
    # complete the same battle — double placements, double rewards, two
    # battle.completed events.
    if not await _claim(battle_id, "completed"):
        return
    for p in ranked:
        await db.get().execute(
            "UPDATE battle_players SET placement = ? WHERE battle_id = ? AND profile_id = ?",
            (placements[p["profile_id"]], battle_id, p["profile_id"]))
    await db.get().commit()
    podium = [{"profile_id": p["profile_id"], "display_name": p["display_name"],
               "power": p["power"], "placement": placements[p["profile_id"]]} for p in ranked]
    await events.publish("battle", battle_id, "battle.completed", battle_id, {"podium": podium})

    from . import character as character_service
    winners = {pid for pid, place in placements.items() if place == 1}
    for p in ranked:
        if demo_multiplayer.is_simulated(p["profile_id"]):
            continue
        outcome = "verified" if p["profile_id"] in winners else "battle_lost"
        await character_service.react(p["profile_id"], "battle_finished", outcome, "battle")


async def resume_battles() -> int:
    """Reconstruct battle timers after a server restart."""
    cur = await db.get().execute("SELECT * FROM battles WHERE state IN ('countdown','active','resolving')")
    rows = [dict(r) for r in await cur.fetchall()]
    for b in rows:
        if b["state"] == "countdown":
            _timers[b["id"]] = asyncio.create_task(_countdown_then_start(b["id"]))
        elif b["state"] == "active" and b["ends_at"]:
            remaining = (parse_iso(b["ends_at"]) - now()).total_seconds()
            _timers[b["id"]] = asyncio.create_task(_auto_finish(b["id"], max(0, remaining)))
        else:
            await maybe_resolve(b["id"])
    return len(rows)


async def battle_results(profile_id: str, battle_id: str) -> dict:
    await _require_player(battle_id, profile_id)
    return await public_battle(battle_id, profile_id)
