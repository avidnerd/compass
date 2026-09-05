"""Deterministic simulated players used by the local product demo.

The roster is intentionally bundled rather than randomly generated so a demo
is repeatable across restarts, screenshots, and test runs. Simulated profiles
are materialized in SQLite only when a user starts a focus room with one.
"""
from datetime import date, timedelta

from .. import db
from ..errors import ApiError
from ..util import now_iso


SIMULATED_PLAYERS: tuple[dict, ...] = (
    {
        "id": "demo-mina-vale", "display_name": "Mina Vale", "handle": "@mossminute",
        "avatar": "leaf", "title": "Steady Sprinter", "status": "online",
        "availability": "Ready now", "companion_name": "Bramble", "companion_species": "mossfox",
        "level": 18, "palette": "meadow", "personality": "gentle",
        "stats": {"focus_minutes": 3180, "focus_streak": 18, "quests_completed": 42, "collaboration": 36},
    },
    {
        "id": "demo-theo-sparks", "display_name": "Theo Sparks", "handle": "@deepworktheo",
        "avatar": "fire", "title": "Steady Closer", "status": "in_focus",
        "availability": "Free in 12 min", "companion_name": "Cinder", "companion_species": "wisp",
        "level": 22, "palette": "ember", "personality": "bold",
        "stats": {"focus_minutes": 2895, "focus_streak": 11, "quests_completed": 34, "collaboration": 31},
    },
    {
        "id": "demo-juniper-sky", "display_name": "Juniper Sky", "handle": "@quietorbit",
        "avatar": "moon", "title": "Night Cartographer", "status": "online",
        "availability": "Ready now", "companion_name": "Orbit", "companion_species": "moonmoth",
        "level": 16, "palette": "midnight", "personality": "curious",
        "stats": {"focus_minutes": 3420, "focus_streak": 26, "quests_completed": 48, "collaboration": 28},
    },
    {
        "id": "demo-cass-reed", "display_name": "Cass Reed", "handle": "@shipshape",
        "avatar": "bolt", "title": "Fast Finisher", "status": "online",
        "availability": "Ready now", "companion_name": "Zip", "companion_species": "sparrow",
        "level": 20, "palette": "aurora", "personality": "cheerful",
        "stats": {"focus_minutes": 2540, "focus_streak": 9, "quests_completed": 39, "collaboration": 33},
    },
    {
        "id": "demo-noor-tide", "display_name": "Noor Tide", "handle": "@softcurrent",
        "avatar": "ball", "title": "Calm Closer", "status": "away",
        "availability": "Back this afternoon", "companion_name": "Ripple", "companion_species": "otterling",
        "level": 14, "palette": "tidepool", "personality": "warm",
        "stats": {"focus_minutes": 2310, "focus_streak": 14, "quests_completed": 31, "collaboration": 39},
    },
    {
        "id": "demo-sage-bloom", "display_name": "Sage Bloom", "handle": "@tinytriumphs",
        "avatar": "terrarium", "title": "Party Anchor", "status": "online",
        "availability": "Ready now", "companion_name": "Button", "companion_species": "sproutling",
        "level": 19, "palette": "meadow", "personality": "playful",
        "stats": {"focus_minutes": 2715, "focus_streak": 21, "quests_completed": 37, "collaboration": 44},
    },
)

_BY_ID = {player["id"]: player for player in SIMULATED_PLAYERS}

def is_simulated(profile_id: str) -> bool:
    return profile_id in _BY_ID


def get_player(profile_id: str) -> dict:
    player = _BY_ID.get(profile_id)
    if player is None:
        raise ApiError(422, "unknown_simulated_player", "That simulated player is not available.")
    return player


def public_player(player: dict) -> dict:
    return dict(player)


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
