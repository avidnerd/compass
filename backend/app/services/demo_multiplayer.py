"""Deterministic simulated players used by the local product demo.

The roster is intentionally bundled rather than randomly generated so a demo
is repeatable across restarts, screenshots, and test runs. Simulated profiles
are materialized in SQLite only when a user starts a party or battle with one.
"""
from datetime import date, timedelta

from .. import db
from ..errors import ApiError
from ..util import now_iso


SIMULATED_PLAYERS: tuple[dict, ...] = (
    {
        "id": "demo-mina-vale", "display_name": "Mina Vale", "handle": "@mossminute",
        "avatar": "🌿", "title": "Steady Sprinter", "status": "online",
        "availability": "Ready now", "companion_name": "Bramble", "companion_species": "mossfox",
        "level": 18, "palette": "meadow", "personality": "gentle", "battle_power": 82,
        "stats": {"focus_minutes": 3180, "focus_streak": 18, "battle_wins": 27,
                  "boss_damage": 14820, "quests_completed": 42, "collaboration": 36},
    },
    {
        "id": "demo-theo-sparks", "display_name": "Theo Sparks", "handle": "@deepworktheo",
        "avatar": "🔥", "title": "Boss Breaker", "status": "in_focus",
        "availability": "Free in 12 min", "companion_name": "Cinder", "companion_species": "wisp",
        "level": 22, "palette": "ember", "personality": "bold", "battle_power": 91,
        "stats": {"focus_minutes": 2895, "focus_streak": 11, "battle_wins": 41,
                  "boss_damage": 22140, "quests_completed": 34, "collaboration": 31},
    },
    {
        "id": "demo-juniper-sky", "display_name": "Juniper Sky", "handle": "@quietorbit",
        "avatar": "🌙", "title": "Night Cartographer", "status": "online",
        "availability": "Ready now", "companion_name": "Orbit", "companion_species": "moonmoth",
        "level": 16, "palette": "midnight", "personality": "curious", "battle_power": 77,
        "stats": {"focus_minutes": 3420, "focus_streak": 26, "battle_wins": 19,
                  "boss_damage": 12670, "quests_completed": 48, "collaboration": 28},
    },
    {
        "id": "demo-cass-reed", "display_name": "Cass Reed", "handle": "@shipshape",
        "avatar": "⚡", "title": "Fast Finisher", "status": "online",
        "availability": "Ready now", "companion_name": "Zip", "companion_species": "sparrow",
        "level": 20, "palette": "aurora", "personality": "cheerful", "battle_power": 86,
        "stats": {"focus_minutes": 2540, "focus_streak": 9, "battle_wins": 35,
                  "boss_damage": 17440, "quests_completed": 39, "collaboration": 33},
    },
    {
        "id": "demo-noor-tide", "display_name": "Noor Tide", "handle": "@softcurrent",
        "avatar": "🫧", "title": "Calm Closer", "status": "away",
        "availability": "Back this afternoon", "companion_name": "Ripple", "companion_species": "otterling",
        "level": 14, "palette": "tidepool", "personality": "warm", "battle_power": 73,
        "stats": {"focus_minutes": 2310, "focus_streak": 14, "battle_wins": 16,
                  "boss_damage": 11380, "quests_completed": 31, "collaboration": 39},
    },
    {
        "id": "demo-sage-bloom", "display_name": "Sage Bloom", "handle": "@tinytriumphs",
        "avatar": "🍄", "title": "Party Anchor", "status": "online",
        "availability": "Ready now", "companion_name": "Button", "companion_species": "sproutling",
        "level": 19, "palette": "meadow", "personality": "playful", "battle_power": 80,
        "stats": {"focus_minutes": 2715, "focus_streak": 21, "battle_wins": 23,
                  "boss_damage": 19860, "quests_completed": 37, "collaboration": 44},
    },
)

_BY_ID = {player["id"]: player for player in SIMULATED_PLAYERS}

LEADERBOARD_METRICS = (
    {"id": "focus_minutes", "label": "Focus time", "short_label": "Focus", "unit": "min", "icon": "⏱️"},
    {"id": "focus_streak", "label": "Focus streak", "short_label": "Streak", "unit": "days", "icon": "🔥"},
    {"id": "battle_wins", "label": "Battle wins", "short_label": "Wins", "unit": "wins", "icon": "⚔️"},
    {"id": "boss_damage", "label": "Boss damage", "short_label": "Damage", "unit": "dmg", "icon": "💥"},
    {"id": "quests_completed", "label": "Quests completed", "short_label": "Quests", "unit": "quests", "icon": "🗺️"},
    {"id": "collaboration", "label": "Collaboration", "short_label": "Co-op", "unit": "pts", "icon": "🤝"},
)


def is_simulated(profile_id: str) -> bool:
    return profile_id in _BY_ID


def get_player(profile_id: str) -> dict:
    player = _BY_ID.get(profile_id)
    if player is None:
        raise ApiError(422, "unknown_simulated_player", "That simulated player is not available.")
    return player


def public_player(player: dict) -> dict:
    return {key: value for key, value in player.items() if key != "battle_power"}


def list_players() -> list[dict]:
    return [public_player(player) for player in SIMULATED_PLAYERS]


def validate_player_ids(profile_ids: list[str], *, limit: int) -> list[str]:
    unique = list(dict.fromkeys(profile_ids))
    if len(unique) > limit:
        raise ApiError(422, "too_many_simulated_players",
                       f"Choose at most {limit} simulated player{'s' if limit != 1 else ''}.")
    for profile_id in unique:
        get_player(profile_id)
    return unique


async def ensure_profiles(profile_ids: list[str]) -> None:
    """Create the minimal FK-backed profile/character rows multiplayer needs."""
    ts = now_iso()
    for profile_id in profile_ids:
        player = get_player(profile_id)
        await db.get().execute(
            """INSERT OR IGNORE INTO profiles
                 (id, display_name, timezone, onboarding_step, recovery_code_hash, created_at, updated_at)
               VALUES (?, ?, 'UTC', 'done', ?, ?, ?)""",
            (profile_id, player["display_name"], f"simulated:{profile_id}", ts, ts))
        stat = player["stats"]
        await db.get().execute(
            """INSERT OR IGNORE INTO characters
                 (profile_id, name, species, palette, habitat, personality, xp, level,
                  stat_focus, stat_curiosity, stat_craft, stat_communication,
                  stat_collaboration, stat_balance, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (profile_id, player["companion_name"], player["companion_species"], player["palette"],
             player["palette"], player["personality"], player["level"] * 120, player["level"],
             min(50, 8 + player["level"]), min(50, 7 + player["level"]),
             min(50, 6 + player["level"]), min(50, 5 + stat["collaboration"] // 2),
             stat["collaboration"], min(50, 10 + stat["focus_streak"] // 2), ts, ts))
    await db.get().commit()


async def _current_player_stats(profile: dict) -> dict[str, int]:
    profile_id = profile["id"]
    cur = await db.get().execute(
        """SELECT COALESCE(SUM(planned_seconds), 0)
           FROM focus_sessions WHERE profile_id = ? AND state = 'completed'""", (profile_id,))
    focus_minutes = round((await cur.fetchone())[0] / 60)

    cur = await db.get().execute(
        """SELECT DISTINCT substr(finished_at, 1, 10) AS day
           FROM focus_sessions
           WHERE profile_id = ? AND state = 'completed' AND finished_at IS NOT NULL
           ORDER BY day DESC""", (profile_id,))
    days = [date.fromisoformat(row["day"]) for row in await cur.fetchall()]
    streak = 0
    if days and days[0] >= date.today() - timedelta(days=1):
        expected = days[0]
        for day in days:
            if day != expected:
                break
            streak += 1
            expected -= timedelta(days=1)

    cur = await db.get().execute(
        "SELECT COUNT(*) FROM battle_players WHERE profile_id = ? AND placement = 1", (profile_id,))
    battle_wins = (await cur.fetchone())[0]
    cur = await db.get().execute(
        "SELECT COALESCE(SUM(damage), 0) FROM boss_contributions WHERE profile_id = ?", (profile_id,))
    boss_damage = (await cur.fetchone())[0]
    cur = await db.get().execute(
        "SELECT COUNT(*) FROM quests WHERE profile_id = ? AND state = 'completed'", (profile_id,))
    quests_completed = (await cur.fetchone())[0]
    cur = await db.get().execute(
        "SELECT stat_collaboration FROM characters WHERE profile_id = ?", (profile_id,))
    character = await cur.fetchone()

    return {
        "focus_minutes": focus_minutes, "focus_streak": streak, "battle_wins": battle_wins,
        "boss_damage": boss_damage, "quests_completed": quests_completed,
        "collaboration": character["stat_collaboration"] if character else 0,
    }


async def leaderboards(profile: dict) -> dict:
    current_stats = await _current_player_stats(profile)
    trend_by_id = {player["id"]: (index % 3) - 1 for index, player in enumerate(SIMULATED_PLAYERS)}
    boards = []
    for metric in LEADERBOARD_METRICS:
        metric_id = metric["id"]
        entries = [
            {
                "profile_id": player["id"], "display_name": player["display_name"],
                "avatar": player["avatar"], "title": player["title"],
                "value": player["stats"][metric_id], "trend": trend_by_id[player["id"]],
                "is_simulated": True, "is_current_user": False,
            }
            for player in SIMULATED_PLAYERS
        ]
        entries.append({
            "profile_id": profile["id"], "display_name": profile["display_name"],
            "avatar": "🧭", "title": "Your trail", "value": current_stats[metric_id],
            "trend": 0, "is_simulated": False, "is_current_user": True,
        })
        entries.sort(key=lambda entry: (-entry["value"], entry["display_name"]))
        previous_value = None
        previous_rank = 0
        for index, entry in enumerate(entries):
            if entry["value"] != previous_value:
                previous_rank = index + 1
                previous_value = entry["value"]
            entry["rank"] = previous_rank
        boards.append({**metric, "entries": entries})

    return {"season": "Meadow League · Week 4", "updated_at": now_iso(), "metrics": boards}
