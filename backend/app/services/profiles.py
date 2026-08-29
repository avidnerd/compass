"""Local identity: profiles, cookie sessions, recovery codes, connections."""
import json
from datetime import timedelta

from .. import cache, capabilities, db
from ..config import settings
from ..errors import ApiError, ProviderError, not_found
from ..util import (new_id, new_recovery_code, new_session_token, now, now_iso, parse_iso, sha256_hex)

ONBOARDING_STEPS = ["connect", "scan", "companion", "quest", "done"]


def public_profile(row: dict) -> dict:
    return {
        "id": row["id"], "display_name": row["display_name"], "timezone": row["timezone"],
        "work_hours_start": row["work_hours_start"], "work_hours_end": row["work_hours_end"],
        "onboarding_step": row["onboarding_step"],
        "share_activity_category": bool(row["share_activity_category"]),
        "scan_consented": bool(row["scan_consented"]),
        "created_at": row["created_at"],
    }


async def get_profile(profile_id: str) -> dict:
    cur = await db.get().execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
    row = await cur.fetchone()
    if row is None:
        raise not_found("profile")
    return dict(row)


async def create_profile(display_name: str, timezone_name: str, work_hours_start: int,
                         work_hours_end: int) -> tuple[dict, str, str]:
    """Returns (profile, session_token, recovery_code). Token/code plaintext
    exist only in this response; only hashes are stored."""
    conn = db.get()
    profile_id = new_id()
    recovery_code = new_recovery_code()
    ts = now_iso()
    await conn.execute(
        """INSERT INTO profiles (id, display_name, timezone, work_hours_start, work_hours_end,
             onboarding_step, recovery_code_hash, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 'connect', ?, ?, ?)""",
        (profile_id, display_name, timezone_name, work_hours_start, work_hours_end,
         sha256_hex(recovery_code), ts, ts))
    await conn.commit()
    token = await issue_session(profile_id)
    profile = await get_profile(profile_id)
    return profile, token, recovery_code


async def issue_session(profile_id: str) -> str:
    token = new_session_token()
    expires = (now() + timedelta(seconds=settings.session_ttl_seconds)).isoformat()
    await db.get().execute(
        "INSERT INTO auth_sessions (id, profile_id, token_hash, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
        (new_id(), profile_id, sha256_hex(token), expires, now_iso()))
    await db.get().commit()
    return token


async def profile_for_token(token: str) -> dict | None:
    cur = await db.get().execute(
        "SELECT s.expires_at, s.id AS session_id, p.* FROM auth_sessions s"
        " JOIN profiles p ON p.id = s.profile_id WHERE s.token_hash = ?",
        (sha256_hex(token),))
    row = await cur.fetchone()
    if row is None or parse_iso(row["expires_at"]) <= now():
        return None
    await db.get().execute("UPDATE auth_sessions SET last_used_at = ? WHERE id = ?",
                           (now_iso(), row["session_id"]))
    await db.get().commit()
    return dict(row)


async def recover(recovery_code: str) -> tuple[dict, str]:
    cur = await db.get().execute("SELECT * FROM profiles WHERE recovery_code_hash = ?",
                                 (sha256_hex(recovery_code.strip().upper()),))
    row = await cur.fetchone()
    if row is None:
        raise ApiError(401, "invalid_recovery_code", "That recovery code did not match any profile.")
    token = await issue_session(row["id"])
    return dict(row), token


async def end_session(token: str) -> None:
    await db.get().execute("DELETE FROM auth_sessions WHERE token_hash = ?", (sha256_hex(token),))
    await db.get().commit()


async def update_profile(profile_id: str, patch: dict) -> dict:
    allowed = {"display_name", "timezone", "work_hours_start", "work_hours_end",
               "onboarding_step", "share_activity_category", "scan_consented"}
    fields = {k: v for k, v in patch.items() if k in allowed and v is not None}
    if "onboarding_step" in fields and fields["onboarding_step"] not in ONBOARDING_STEPS:
        raise ApiError(422, "invalid_request", "Unknown onboarding step.")
    if fields:
        cols = ", ".join(f"{k} = ?" for k in fields)
        await db.get().execute(f"UPDATE profiles SET {cols}, updated_at = ? WHERE id = ?",
                               (*fields.values(), now_iso(), profile_id))
        await db.get().commit()
    return await get_profile(profile_id)


async def delete_profile(profile_id: str) -> None:
    from .. import focus_monitoring
    from . import college
    await focus_monitoring.cleanup_profile_frames(profile_id)
    await cache.delete_profile_caches(profile_id)
    college.forget_memo(profile_id)
    await db.get().execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
    await db.get().commit()


# ------------------------------------------------------------- connections

async def validate_connections(profile: dict, force: bool = False) -> list[dict]:
    """Per-connector credential validation, cached 5 minutes per profile."""
    from .. import providers, telemetry
    results = []
    reg = capabilities.current_registry()
    conn = db.get()
    provider = await providers.active_provider(profile)
    for connector in capabilities.CONNECTORS:
        status, error_code, caps = "unknown", None, []
        if connector == "canvas":
            # Canvas is not served by the Apps Script bridge: it is a calendar
            # feed the student links directly, so it stands or falls on its own
            # credential and must not inherit the bridge's status.
            from .canvas import public_link as canvas_link
            link = await canvas_link(profile["id"])
            if link["status"] != "linked":
                status = "disconnected"
            else:
                status = "error" if link.get("connection_status") == "error" else "connected"
                error_code = link.get("error_code")
            caps = ["canvas.assignments"]
        elif provider is None:
            status, error_code = "error", "provider_not_configured"
        elif reg is None:
            status, error_code = "unknown", "capabilities_pending"
        elif reg.resolve(f"{connector}.validate") is None:
            status = "unsupported" if reg.connector_status(connector) == "unsupported" else "degraded"
            caps = reg.capabilities_for(connector)
        else:
            caps = reg.capabilities_for(connector)
            try:
                payload, _meta = await telemetry.call_capability(
                    profile, f"{connector}.validate", {},
                    ttl_seconds=settings.ttl_credential_validation, force=force, connector=connector)
                status = "connected" if payload.get("success") else "disconnected"
            except ApiError as exc:
                status, error_code = "error", exc.code
            except ProviderError as exc:
                # A provider that says "not configured" means this connector is
                # simply not linked yet, not that something broke.
                status = "disconnected" if exc.code.endswith("_not_configured") else "error"
                error_code = exc.code
        await conn.execute(
            """INSERT INTO connector_states (profile_id, connector, status, capabilities_json, last_checked_at, error_code)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(profile_id, connector) DO UPDATE SET
                 status = excluded.status, capabilities_json = excluded.capabilities_json,
                 last_checked_at = excluded.last_checked_at, error_code = excluded.error_code""",
            (profile["id"], connector, status, json.dumps(caps), now_iso(), error_code))
        results.append({"connector": connector, "status": status, "error_code": error_code,
                        "capabilities": caps, "last_checked_at": now_iso()})
    await conn.commit()
    return results


async def connector_states(profile_id: str) -> list[dict]:
    cur = await db.get().execute(
        "SELECT * FROM connector_states WHERE profile_id = ? ORDER BY connector", (profile_id,))
    rows = await cur.fetchall()
    return [{"connector": r["connector"], "status": r["status"], "error_code": r["error_code"],
             "capabilities": json.loads(r["capabilities_json"] or "[]"),
             "last_checked_at": r["last_checked_at"], "generation": r["generation"]}
            for r in rows]


async def manual_refresh_allowed(profile_id: str, connector: str) -> bool:
    cur = await db.get().execute(
        "SELECT last_manual_refresh_at FROM connector_states WHERE profile_id = ? AND connector = ?",
        (profile_id, connector))
    row = await cur.fetchone()
    if row is None or not row["last_manual_refresh_at"]:
        return True
    return (now() - parse_iso(row["last_manual_refresh_at"])).total_seconds() >= 60


async def mark_manual_refresh(profile_id: str, connector: str) -> None:
    await db.get().execute(
        """INSERT INTO connector_states (profile_id, connector, last_manual_refresh_at) VALUES (?, ?, ?)
           ON CONFLICT(profile_id, connector) DO UPDATE SET last_manual_refresh_at = excluded.last_manual_refresh_at""",
        (profile_id, connector, now_iso()))
    await db.get().commit()


async def export_profile(profile_id: str) -> dict:
    """Local JSON export of everything this profile owns."""
    conn = db.get()
    out: dict = {"exported_at": now_iso()}
    tables = {
        "profile": ("SELECT id, display_name, timezone, work_hours_start, work_hours_end, "
                    "onboarding_step, created_at FROM profiles WHERE id = ?"),
        "interest_profile": "SELECT * FROM interest_profiles WHERE profile_id = ?",
        "character": "SELECT * FROM characters WHERE profile_id = ?",
        "memories": "SELECT * FROM character_memories WHERE profile_id = ?",
        "quests": "SELECT * FROM quests WHERE profile_id = ?",
        "subgoals": "SELECT * FROM subgoals WHERE profile_id = ?",
        "focus_sessions": "SELECT * FROM focus_sessions WHERE profile_id = ?",
        "verifications": "SELECT * FROM verifications WHERE profile_id = ?",
        "evidence": "SELECT * FROM evidence_items WHERE profile_id = ?",
        "focus_frame_metadata": "SELECT * FROM focus_frames WHERE profile_id = ?",
        "stat_ledger": "SELECT * FROM stat_ledger WHERE profile_id = ?",
        # College OS link + import ledger (file ids and which sheet row became
        # which quest — never dashboard cell content).
        "college_link": "SELECT * FROM college_links WHERE profile_id = ?",
        "college_imports": "SELECT * FROM college_imports WHERE profile_id = ?",
    }
    for key, sql in tables.items():
        cur = await conn.execute(sql, (profile_id,))
        rows = [dict(r) for r in await cur.fetchall()]
        out[key] = (rows[0] if key in ("profile", "interest_profile", "character", "college_link")
                    and rows else rows)
    return out
