"""Identity, onboarding, connections, interest scan, jobs, system, cache."""
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from .. import cache, capabilities, jobs, openrouter, providers
from ..api import COOKIE_NAME, CurrentProfile, envelope, set_session_cookie
from ..config import settings
from ..errors import ApiError, not_found
from ..services import college as college_service
from ..services import interest as interest_service
from ..services import profiles as profile_service

router = APIRouter()


class CreateProfileBody(BaseModel):
    display_name: str = Field(min_length=1, max_length=60)
    timezone: str = "UTC"
    work_hours_start: int = Field(default=9, ge=0, le=23)
    work_hours_end: int = Field(default=18, ge=1, le=24)


@router.post("/profiles", status_code=201)
async def create_profile(body: CreateProfileBody, request: Request, response: Response):
    profile, token, recovery_code = await profile_service.create_profile(
        body.display_name.strip(), body.timezone, body.work_hours_start, body.work_hours_end)
    set_session_cookie(response, token, secure=settings.public_mode)
    return envelope({
        "profile": profile_service.public_profile(profile),
        "recovery_code": recovery_code,  # shown exactly once
    }, request)


class RecoverBody(BaseModel):
    recovery_code: str = Field(min_length=8, max_length=40)


@router.post("/auth/recover")
async def recover(body: RecoverBody, request: Request, response: Response):
    profile, token = await profile_service.recover(body.recovery_code)
    set_session_cookie(response, token, secure=settings.public_mode)
    return envelope({"profile": profile_service.public_profile(profile)}, request)


@router.delete("/auth/session")
async def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        await profile_service.end_session(token)
    response.delete_cookie(COOKIE_NAME, path="/")
    return envelope({"logged_out": True}, request)


@router.get("/me")
async def me(request: Request, profile: dict = CurrentProfile):
    return envelope(profile_service.public_profile(profile), request)


class PatchMeBody(BaseModel):
    display_name: str | None = Field(default=None, max_length=60)
    timezone: str | None = None
    work_hours_start: int | None = Field(default=None, ge=0, le=23)
    work_hours_end: int | None = Field(default=None, ge=1, le=24)
    onboarding_step: str | None = None
    share_activity_category: bool | None = None
    scan_consented: bool | None = None


@router.patch("/me")
async def patch_me(body: PatchMeBody, request: Request, profile: dict = CurrentProfile):
    updated = await profile_service.update_profile(profile["id"], body.model_dump(exclude_none=True))
    return envelope(profile_service.public_profile(updated), request)


@router.delete("/me")
async def delete_me(request: Request, response: Response, profile: dict = CurrentProfile):
    await profile_service.delete_profile(profile["id"])
    response.delete_cookie(COOKIE_NAME, path="/")
    return envelope({"deleted": True}, request)


@router.get("/me/export")
async def export_me(request: Request, profile: dict = CurrentProfile):
    return envelope(await profile_service.export_profile(profile["id"]), request)


@router.get("/onboarding")
async def onboarding(request: Request, profile: dict = CurrentProfile):
    ip = await interest_service.get_interest_profile(profile["id"])
    return envelope({
        "step": profile["onboarding_step"],
        "steps": profile_service.ONBOARDING_STEPS,
        "scan_consented": bool(profile["scan_consented"]),
        "has_interest_profile": ip is not None,
    }, request)


@router.get("/connections")
async def connections(request: Request, refresh: bool = False, profile: dict = CurrentProfile):
    if refresh or not await profile_service.connector_states(profile["id"]):
        states = await profile_service.validate_connections(profile, force=refresh)
    else:
        states = await profile_service.connector_states(profile["id"])
    return envelope(states, request)


# ------------------------------------------------------- the data provider

@router.get("/providers")
async def provider_state(request: Request, profile: dict = CurrentProfile):
    return envelope(await providers.public_state(profile["id"]), request)


class BridgeBody(BaseModel):
    url: str = Field(min_length=1, max_length=500)
    token: str = Field(min_length=8, max_length=200)


@router.put("/providers/bridge")
async def save_bridge(body: BridgeBody, request: Request, profile: dict = CurrentProfile):
    """Verify an Apps Script bridge deployment, then adopt it for this profile."""
    url, token = body.url.strip(), body.token.strip()
    hello = await providers.verify_bridge(profile["id"], url, token)
    state = await providers.save_credentials(profile["id"], "bridge", {"url": url, "token": token})
    await capabilities.discover_bridge_capabilities(force=True)
    await profile_service.validate_connections(profile, force=True)
    return envelope({**state, "handshake": hello}, request)


@router.delete("/providers/bridge")
async def clear_bridge(request: Request, profile: dict = CurrentProfile):
    return envelope(await providers.delete_credentials(profile["id"], "bridge"), request)


class GitHubBody(BaseModel):
    token: str = Field(min_length=8, max_length=255)


@router.put("/providers/github")
async def save_github(body: GitHubBody, request: Request, profile: dict = CurrentProfile):
    token = body.token.strip()
    result = await providers.verify_github(profile["id"], token)
    if not result.get("success"):
        raise ApiError(400, "github_unauthorized", "GitHub did not accept that token.")
    state = await providers.save_credentials(profile["id"], "github", {"token": token})
    return envelope(state, request)


@router.delete("/providers/github")
async def clear_github(request: Request, profile: dict = CurrentProfile):
    return envelope(await providers.delete_credentials(profile["id"], "github"), request)


@router.post("/connections/{connector}:refresh")
async def refresh_connector(connector: str, request: Request, profile: dict = CurrentProfile):
    if connector not in capabilities.CONNECTORS:
        raise ApiError(422, "invalid_request", f"Unknown connector: {connector}")
    if not await profile_service.manual_refresh_allowed(profile["id"], connector):
        raise ApiError(429, "refresh_cooldown", "Manual refresh is limited to once per minute.")
    await profile_service.mark_manual_refresh(profile["id"], connector)
    invalidated = await cache.invalidate_connector(profile["id"], connector)
    states = await profile_service.validate_connections(profile, force=True)
    return envelope({"invalidated_rows": invalidated, "connections": states}, request)


@router.post("/interest-scans", status_code=202)
async def start_scan(request: Request, profile: dict = CurrentProfile):
    job = await interest_service.start_interest_scan(profile)
    return envelope(jobs.public_view(job), request)


@router.get("/interest-profile")
async def get_interest(request: Request, profile: dict = CurrentProfile):
    ip = await interest_service.get_interest_profile(profile["id"])
    if ip is None:
        raise not_found("interest profile")
    return envelope(ip, request)


@router.patch("/interest-profile")
async def patch_interest(request: Request, profile: dict = CurrentProfile):
    body = await request.json()
    ip = await interest_service.patch_interest_profile(profile["id"], body or {})
    return envelope(ip, request)


@router.post("/interest-profile:rescan", status_code=202)
async def rescan(request: Request, profile: dict = CurrentProfile):
    job = await interest_service.start_interest_scan(profile)
    return envelope(jobs.public_view(job), request)


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request, profile: dict = CurrentProfile):
    job = await jobs.job_row(job_id)
    if job is None:
        raise not_found("job")
    if job["profile_id"] and job["profile_id"] != profile["id"]:
        raise ApiError(403, "forbidden", "Not your job.")
    return envelope(jobs.public_view(job), request)


@router.get("/system/free-models")
async def free_models(request: Request, profile: dict = CurrentProfile):
    """Model IDs, availability, and selection only — never keys or pricing."""
    prefs = openrouter.preference_order()
    selected = None
    statuses: list[dict] = [{"id": m, "status": "unknown"} for m in prefs]
    scan_model = None
    checked_at = None
    if settings.openrouter_api_key:
        try:
            catalog = await openrouter.refresh_free_model_catalog()
            statuses = openrouter.evaluate_preferences(catalog, prefs)
            model = await openrouter.resolve_free_model()
            selected = model.id if model else None
            checked_at = True
            if settings.openrouter_scan_model:
                scan_candidates = await openrouter.resolve_candidates(
                    limit=1, preferences=[settings.openrouter_scan_model],
                    allow_missing_structured=True)
                scan_model = {
                    "id": settings.openrouter_scan_model,
                    "status": "verified_free"
                    if (scan_candidates and scan_candidates[0].id == settings.openrouter_scan_model)
                    else "rejected_not_free",
                }
        except Exception:
            pass
    auth = openrouter.auth_state()
    return envelope({
        "configured": bool(settings.openrouter_api_key),
        "models": statuses,
        "selected_model": selected,
        "scan_model": scan_model,
        "available": selected is not None and auth != "failed",
        "auth_state": auth,
        "catalog_checked": bool(checked_at),
    }, request)


@router.get("/cache/stats")
async def cache_stats(request: Request, profile: dict = CurrentProfile):
    return envelope(await cache.cache_stats(profile["id"]), request)


@router.post("/cache/{connector}:invalidate")
async def invalidate_cache(connector: str, request: Request, profile: dict = CurrentProfile):
    if connector not in capabilities.CONNECTORS:
        raise ApiError(422, "invalid_request", f"Unknown connector: {connector}")
    n = await cache.invalidate_connector(profile["id"], connector)
    if connector in ("google_sheets", "google_drive"):
        college_service.forget_memo(profile["id"])
    return envelope({"invalidated_rows": n}, request)


@router.get("/system/health")
async def health(request: Request):
    reg = capabilities.current_registry()
    return envelope({
        "status": "ok",
        "capabilities_discovered": reg is not None,
        "missing_capabilities": reg.missing if reg else None,
        "demo_mode": settings.demo_mode,
    }, request)
