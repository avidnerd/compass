"""Compass application: API v1, WebSocket, background workers, and the built
SPA served from one local process."""
import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import bridge, capabilities, crypto, db, focus_monitoring, github, jobs, openrouter, providers
from .config import REPO_ROOT, settings
from .errors import ApiError, ProviderError
from .routers import college, game, identity, insights_router, multiplayer, canvas as canvas_router
from .services import canvas as canvas_service, postcards
from .ws import router as ws_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("compass.main")

# An installed copy has no repo to read from, so the built interface ships
# inside the package (packaging copies frontend/dist -> app/web). A source
# checkout keeps using frontend/dist so `make dev` needs no extra step.
_BUNDLED_WEB = Path(__file__).resolve().parent / "web"
SPA_DIST = _BUNDLED_WEB if (_BUNDLED_WEB / "index.html").exists() else REPO_ROOT / "frontend" / "dist"

_background: list[asyncio.Task] = []


async def _discover_capabilities_startup() -> None:
    """Install the capability registry.

    Nothing is discovered over the network any more: the Apps Script bridge
    answers logical capability names directly, so its surface is fixed and the
    registry is the same whether or not a profile has adopted it yet.
    """
    registry = await capabilities.discover_bridge_capabilities(force=True)
    if not await providers.any_bridge_configured():
        logger.warning("[startup] no data provider configured; connector features disabled "
                       "(deploy college-os/bridge/api.gs and add it in Settings → Connections)")
        return
    logger.info("[startup] Apps Script bridge active: %d capabilities, %d unavailable",
                len(registry.available), len(registry.missing))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    await db.run_migrations()
    if not crypto.available():
        logger.warning("[startup] COMPASS_APP_SECRET is not set — provider credentials will be "
                       "stored unencrypted. Set it in .env and re-save them.")
    removed_frames = await focus_monitoring.cleanup_orphaned_raw_frames()
    if removed_frames:
        logger.info("[startup] removed %d stale raw focus frame(s)", removed_frames)
    await _discover_capabilities_startup()
    if settings.openrouter_api_key:
        try:
            model = await openrouter.resolve_free_model()
            logger.info("[startup] free model: %s", model.id if model else "none available")
        except Exception:
            logger.warning("[startup] OpenRouter catalog unavailable")
    jobs.start_workers()
    requeued = await jobs.resume_jobs()
    if requeued:
        logger.info("[startup] requeued %d interrupted job(s)", requeued)
    _background.append(asyncio.create_task(postcards.postcard_loop()))
    yield
    for t in _background:
        t.cancel()
    await jobs.stop_workers()
    await bridge.aclose()
    await canvas_service.aclose()
    await github.aclose()
    await openrouter.aclose()
    await db.close()


app = FastAPI(title="Compass", lifespan=lifespan, docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins(),
    allow_origin_regex=None if settings.public_mode else r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = uuid.uuid4().hex[:12]

    # Origin validation for mutating cookie-authenticated requests.
    if request.method in ("POST", "PATCH", "PUT", "DELETE"):
        origin = request.headers.get("origin")
        if origin is not None and not settings.origin_allowed(origin):
            return JSONResponse(status_code=403, content={"error": {
                "code": "bad_origin", "message": "Cross-origin request rejected.",
                "details": None, "request_id": request.state.request_id}})
        if settings.public_mode and origin is None and request.url.path.startswith("/api/"):
            return JSONResponse(status_code=403, content={"error": {
                "code": "origin_required", "message": "Origin header required in public mode.",
                "details": None, "request_id": request.state.request_id}})

    response = await call_next(request)
    response.headers["X-Request-Id"] = request.state.request_id
    return response


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status, content={"error": {
        "code": exc.code, "message": exc.message, "details": exc.details,
        "request_id": getattr(request.state, "request_id", None)}})


@app.exception_handler(ProviderError)
async def provider_error_handler(request: Request, exc: ProviderError):
    """Covers the Apps Script bridge and GitHub alike."""
    return JSONResponse(status_code=502, content={"error": {
        "code": exc.code, "message": str(exc) or "A connected-data request failed.",
        "details": None, "request_id": getattr(request.state, "request_id", None)}})


API_PREFIX = "/api/v1"
app.include_router(identity.router, prefix=API_PREFIX)
app.include_router(game.router, prefix=API_PREFIX)
app.include_router(multiplayer.router, prefix=API_PREFIX)
app.include_router(insights_router.router, prefix=API_PREFIX)
app.include_router(college.router, prefix=API_PREFIX)
app.include_router(canvas_router.router, prefix=API_PREFIX)
app.include_router(ws_router)


# ---- Local release build: serve the compiled SPA from this process. -------

if SPA_DIST.exists():
    app.mount("/assets", StaticFiles(directory=SPA_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        candidate = (SPA_DIST / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(SPA_DIST):
            return FileResponse(candidate)
        return FileResponse(SPA_DIST / "index.html")
