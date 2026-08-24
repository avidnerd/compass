"""Client for the College OS Apps Script bridge (`college-os/bridge/api.gs`).

How Compass reads the Google connectors: the user deploys a read-only Apps
Script Web App in their own account and Compass calls it with a shared token.
The script runs under the user's own OAuth grant, so there is no connector
platform, no Cloud project, and no bill.
"""
import asyncio
import json
import logging

import httpx

from .errors import ProviderError

logger = logging.getLogger("compass.bridge")

# Apps Script serialises executions per user anyway; two in flight is plenty.
_semaphore = asyncio.Semaphore(2)

_client: httpx.AsyncClient | None = None


class BridgeError(ProviderError):
    """Safe, redacted Apps Script bridge failure."""


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        # /exec answers with a 302 to script.googleusercontent.com; the body
        # lives at the redirect target.
        _client = httpx.AsyncClient(timeout=60.0, follow_redirects=True)
    return _client


async def aclose() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _validate_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise BridgeError("bridge_not_configured", "No Apps Script bridge URL is configured.")
    if not url.startswith("https://script.google.com/"):
        raise BridgeError("bridge_url_invalid",
                          "The bridge URL must be the https://script.google.com/…/exec deployment URL.")
    return url


async def call(url: str, token: str, capability: str, arguments: dict) -> dict:
    """Invoke one logical capability on the bridge."""
    url = _validate_url(url)
    if not token:
        raise BridgeError("bridge_not_configured", "No Apps Script bridge token is configured.")

    params = {"token": token, "fn": capability, "args": json.dumps(arguments or {}, default=str)}
    logger.info("[bridge] outbound %s", capability)
    async with _semaphore:
        try:
            resp = await client().get(url, params=params)
        except httpx.HTTPError as exc:
            logger.warning("[bridge] transport error on %s: %s", capability, type(exc).__name__)
            raise BridgeError("bridge_unreachable", "Could not reach the Apps Script bridge.") from exc

    if resp.status_code >= 400:
        logger.warning("[bridge] %s returned %s", capability, resp.status_code)
        raise BridgeError(f"bridge_http_{resp.status_code}",
                          f"The Apps Script bridge returned {resp.status_code}.")

    try:
        payload = resp.json()
    except ValueError as exc:
        # Almost always a deployment whose access is not "Anyone": Google serves
        # a sign-in page instead of the script's own JSON.
        raise BridgeError(
            "bridge_not_public",
            "The bridge returned a Google sign-in page. Redeploy the Web App with "
            "\"Who has access: Anyone\".") from exc

    if isinstance(payload, dict) and payload.get("error"):
        error = payload["error"] if isinstance(payload["error"], dict) else {}
        code = str(error.get("code") or "bridge_error")
        if code == "unauthorized":
            raise BridgeError("bridge_unauthorized",
                              "The bridge rejected the token. Re-copy it from setUpBridge().")
        if code == "capability_unsupported":
            raise BridgeError("capability_unsupported", f"The bridge does not serve {capability}.")
        logger.warning("[bridge] %s failed: %s", capability, code)
        raise BridgeError("bridge_tool_error", f"The bridge could not complete {capability}.")

    return payload if isinstance(payload, dict) else {"result": payload}


async def hello(url: str, token: str) -> dict:
    """Handshake used when saving credentials — proves URL, token, and scopes."""
    payload = await call(url, token, "bridge.hello", {})
    return {"ok": bool(payload.get("ok")),
            "capabilities": payload.get("capabilities") or [],
            "timezone": payload.get("timezone")}
