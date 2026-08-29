"""Data-plane credentials and dispatch.

Everything Compass reads from a connected account goes through one logical
capability name (`drive.list_files`, `github.get_commits`, …), answered by the
**bridge** path: a read-only Apps Script Web App the user deploys in their own
Google account (`college-os/bridge/api.gs`), plus a GitHub personal access
token. No connector platform, no Cloud project, no bill.

Credentials are per profile, seeded from the workspace `.env` when present.
They are secrets: encrypted at rest with the app secret (see `crypto`), and
`public_state()` is the only thing an endpoint may return.
"""
import json
import logging

from . import bridge, crypto, db, github
from .config import settings
from .errors import ApiError, ProviderError
from .util import now_iso

logger = logging.getLogger("compass.providers")

BRIDGE = "bridge"

# What the Apps Script bridge can serve. Google Meet is absent on purpose: its
# API needs a Cloud project, which is exactly the cost this path avoids.
BRIDGE_GOOGLE_CAPABILITIES = [
    "drive.list_files", "drive.search_files", "docs.get_text",
    "sheets.get_values", "sheets.get_metadata", "slides.get_presentation",
    "calendar.list_events", "calendar.list_calendars",
    "gmail.list_messages", "gmail.get_message",
]
BRIDGE_GITHUB_CAPABILITIES = [
    "github.get_repositories", "github.get_commits", "github.get_pull_requests",
]
# connector -> the read used to prove the grant still works.
_VALIDATION_PROBE = {
    "google_drive": ("drive.list_files", {"page_size": 1}),
    "google_docs": ("drive.list_files", {"page_size": 1}),
    "google_sheets": ("drive.list_files", {"page_size": 1}),
    "google_slides": ("drive.list_files", {"page_size": 1}),
    "google_calendar": ("calendar.list_calendars", {"max_results": 1}),
    "gmail": ("gmail.list_messages", {"maxResults": 1}),
}


def bridge_capabilities() -> list[str]:
    """Every capability this path can answer, validators included."""
    caps = list(BRIDGE_GOOGLE_CAPABILITIES) + list(BRIDGE_GITHUB_CAPABILITIES)
    caps += [f"{connector}.validate" for connector in _VALIDATION_PROBE]
    caps.append("github.validate")
    return sorted(set(caps))


# ------------------------------------------------------------- credentials

def _env_defaults() -> dict:
    """Workspace-level credentials, used by any profile without its own."""
    out: dict = {}
    if settings.bridge_url and settings.bridge_token:
        out["bridge"] = {"url": settings.bridge_url, "token": settings.bridge_token}
    if settings.github_token:
        out["github"] = {"token": settings.github_token}
    return out


async def credentials(profile_id: str) -> dict:
    """Resolved credentials for a profile: its own rows over the env defaults."""
    resolved = _env_defaults()
    cur = await db.get().execute(
        "SELECT provider, config_json FROM provider_credentials WHERE profile_id = ?", (profile_id,))
    for row in await cur.fetchall():
        try:
            config = json.loads(crypto.unseal(row["config_json"] or "{}"))
        except json.JSONDecodeError:
            continue
        if config:
            resolved[row["provider"]] = config
    return resolved


async def save_credentials(profile_id: str, provider: str, config: dict) -> dict:
    if provider not in (BRIDGE, "github", "canvas"):
        raise ApiError(422, "invalid_request", f"Unknown provider: {provider}")
    await db.get().execute(
        """INSERT INTO provider_credentials (profile_id, provider, config_json, status, updated_at)
           VALUES (?, ?, ?, 'unknown', ?)
           ON CONFLICT(profile_id, provider) DO UPDATE SET
             config_json = excluded.config_json, status = 'unknown',
             error_code = NULL, updated_at = excluded.updated_at""",
        (profile_id, provider, crypto.seal(json.dumps(config)), now_iso()))
    await db.get().commit()
    return await public_state(profile_id)


async def delete_credentials(profile_id: str, provider: str) -> dict:
    await db.get().execute(
        "DELETE FROM provider_credentials WHERE profile_id = ? AND provider = ?",
        (profile_id, provider))
    await db.get().commit()
    return await public_state(profile_id)


async def _mark(profile_id: str, provider: str, status: str, error_code: str | None) -> None:
    await db.get().execute(
        """INSERT INTO provider_credentials (profile_id, provider, config_json, status, error_code,
             last_checked_at, updated_at)
           VALUES (?, ?, '{}', ?, ?, ?, ?)
           ON CONFLICT(profile_id, provider) DO UPDATE SET
             status = excluded.status, error_code = excluded.error_code,
             last_checked_at = excluded.last_checked_at""",
        (profile_id, provider, status, error_code, now_iso(), now_iso()))
    await db.get().commit()


def _mask(secret: str) -> str:
    secret = secret or ""
    return f"…{secret[-4:]}" if len(secret) > 4 else "set"


async def public_state(profile_id: str) -> dict:
    """Safe view for the API. Never returns a URL or token in full."""
    resolved = await credentials(profile_id)
    env = _env_defaults()
    cur = await db.get().execute(
        "SELECT provider, status, error_code, last_checked_at FROM provider_credentials WHERE profile_id = ?",
        (profile_id,))
    marks = {r["provider"]: dict(r) for r in await cur.fetchall()}

    bridge_config = resolved.get("bridge") or {}
    github_config = resolved.get("github") or {}
    return {
        "active": await active_provider_for(resolved),
        "bridge": {
            "configured": bool(bridge_config.get("url") and bridge_config.get("token")),
            "from_env": "bridge" in env and "bridge" not in marks,
            "token_hint": _mask(bridge_config.get("token", "")) if bridge_config else None,
            "status": (marks.get("bridge") or {}).get("status", "unknown"),
            "error_code": (marks.get("bridge") or {}).get("error_code"),
            "last_checked_at": (marks.get("bridge") or {}).get("last_checked_at"),
        },
        "github": {
            "configured": bool(github_config.get("token")),
            "from_env": "github" in env and "github" not in marks,
            "token_hint": _mask(github_config.get("token", "")) if github_config else None,
            "status": (marks.get("github") or {}).get("status", "unknown"),
            "error_code": (marks.get("github") or {}).get("error_code"),
        },
    }


# --------------------------------------------------------------- selection

async def active_provider_for(resolved: dict) -> str | None:
    config = resolved.get("bridge") or {}
    return BRIDGE if config.get("url") and config.get("token") else None


async def active_provider(profile: dict) -> str | None:
    return await active_provider_for(await credentials(profile["id"]))


async def any_bridge_configured() -> bool:
    """Whether the bridge is set up anywhere — used at startup, before any
    particular profile is known."""
    if _env_defaults().get("bridge"):
        return True
    cur = await db.get().execute(
        "SELECT config_json FROM provider_credentials WHERE provider = 'bridge'")
    for row in await cur.fetchall():
        try:
            config = json.loads(crypto.unseal(row["config_json"] or "{}"))
        except json.JSONDecodeError:
            continue
        if config.get("url") and config.get("token"):
            return True
    return False


# ---------------------------------------------------------------- dispatch

async def call(profile: dict, capability: str, arguments: dict) -> dict:
    """Answer one logical capability for this profile."""
    resolved = await credentials(profile["id"])
    if await active_provider_for(resolved) is None:
        raise ApiError(503, "provider_not_configured",
                       "No data provider is set up. Add the Apps Script bridge in "
                       "Settings → Connections.")
    return await _call_bridge(resolved, capability, arguments)


async def _call_bridge(resolved: dict, capability: str, arguments: dict) -> dict:
    if capability.startswith("github."):
        token = (resolved.get("github") or {}).get("token")
        if not token:
            raise github.GitHubError(
                "github_not_configured",
                "No GitHub token yet. Add one in Settings → Connections to track code work.")
        return await github.call(token, capability, arguments)

    connector, _, verb = capability.partition(".")
    if verb == "validate":
        probe = _VALIDATION_PROBE.get(connector)
        if probe is None:
            raise bridge.BridgeError("capability_unsupported",
                                     f"The bridge does not serve {connector}.")
        config = resolved["bridge"]
        await bridge.call(config["url"], config["token"], probe[0], probe[1])
        return {"success": True, "message": "ok"}

    config = resolved["bridge"]
    return await bridge.call(config["url"], config["token"], capability, arguments)


# -------------------------------------------------------------- handshakes

async def verify_bridge(profile_id: str, url: str, token: str) -> dict:
    """Prove a URL/token pair works before trusting it. Never stores on failure."""
    try:
        result = await bridge.hello(url, token)
    except ProviderError as exc:
        await _mark(profile_id, "bridge", "error", exc.code)
        raise
    await _mark(profile_id, "bridge", "ok", None)
    return result


async def verify_github(profile_id: str, token: str) -> dict:
    try:
        result = await github.validate(token)
    except ProviderError as exc:
        await _mark(profile_id, "github", "error", exc.code)
        raise
    await _mark(profile_id, "github", "ok" if result.get("success") else "error",
                None if result.get("success") else "github_unauthorized")
    return result
