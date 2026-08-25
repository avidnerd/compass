"""Compass settings, loaded from the workspace-root .env.

Server-only secrets (the bridge token, the GitHub PAT, the OpenRouter key, the
app secret) never leave this module except through the clients that need them;
no endpoint may echo them.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = REPO_ROOT / ".env"
# override=True: the workspace .env is the authoritative config for this local
# app — a stale OPENROUTER_API_KEY/COMPASS_* exported in the user's shell
# profile must not silently win over it.
load_dotenv(ENV_PATH, override=True)


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    openrouter_api_base: str = os.environ.get("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1")

    # --- Data plane ---------------------------------------------------------
    # A read-only Apps Script Web App the user deploys in their own Google
    # account (college-os/bridge/api.gs), plus a GitHub read-only PAT. Set here
    # they apply to every local profile; Settings → Connections can override
    # them per profile. Nothing else can read a connected account.
    bridge_url: str = os.environ.get("COMPASS_BRIDGE_URL", "").strip()
    bridge_token: str = os.environ.get("COMPASS_BRIDGE_TOKEN", "").strip()
    github_token: str = os.environ.get("COMPASS_GITHUB_TOKEN", "").strip()
    # Drive lists everything the account can see, which includes files other
    # people have shared in. Their names and contents are attacker-controlled
    # input to the scan and to verification. Setting this restricts every Drive
    # read to files the user owns. Needs a bridge redeployed from the current
    # api.gs; older deployments ignore the flag.
    drive_owned_only: bool = _bool("COMPASS_DRIVE_OWNED_ONLY", False)

    openrouter_api_key: str | None = os.environ.get("OPENROUTER_API_KEY")
    openrouter_model: str = os.environ.get("OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free")
    # Preferred model for the interest scan specifically (still verified free
    # at runtime; falls back to the default chain if it doesn't qualify).
    openrouter_scan_model: str = os.environ.get(
        "OPENROUTER_SCAN_MODEL", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free")
    # Preferred model for evidence verification (reasoning model by default).
    openrouter_verify_model: str = os.environ.get(
        "OPENROUTER_VERIFY_MODEL", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free")
    # Preferred free multimodal model for private focus-frame analysis. It is
    # still catalog-verified as free, zero-priced, and image-capable at runtime.
    openrouter_focus_model: str = os.environ.get(
        "OPENROUTER_FOCUS_MODEL", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free")
    # Persist the content excerpt verification read onto the evidence card.
    # Off by default: it relaxes the no-raw-content rule by writing file
    # excerpts into your local DB. Turn it on only to debug a verification.
    debug_evidence: bool = _bool("COMPASS_DEBUG_EVIDENCE", False)
    # Per-file cap on content read for verification (~6k tokens at 24k chars;
    # both default models have ~256k-token contexts).
    verify_excerpt_chars: int = _int("COMPASS_VERIFY_EXCERPT_CHARS", 24000)
    focus_frame_interval_seconds: int = max(
        10, min(_int("COMPASS_FOCUS_FRAME_INTERVAL_SECONDS", 20), 120))
    focus_frame_max_bytes: int = max(
        100_000, min(_int("COMPASS_FOCUS_FRAME_MAX_BYTES", 2_000_000), 5_000_000))
    focus_frame_batch_size: int = max(
        1, min(_int("COMPASS_FOCUS_FRAME_BATCH_SIZE", 4), 6))
    retain_focus_frames: bool = _bool("COMPASS_RETAIN_FOCUS_FRAMES", False)
    openrouter_fallback_models: list[str] = [
        m.strip()
        for m in os.environ.get(
            "OPENROUTER_FALLBACK_MODELS",
            "openai/gpt-oss-20b:free,nvidia/nemotron-3-super-120b-a12b:free,nvidia/nemotron-nano-9b-v2:free",
        ).split(",")
        if m.strip()
    ]

    # Derives the key that encrypts provider credentials at rest (see crypto).
    # Changing it makes stored bridge/GitHub tokens unreadable — they then have
    # to be re-entered in Settings → Connections.
    app_secret: str = os.environ.get("COMPASS_APP_SECRET", "")
    frontend_origin: str = os.environ.get("COMPASS_FRONTEND_ORIGIN", "http://localhost:5173")
    timezone: str = os.environ.get("COMPASS_TIMEZONE", "UTC")
    bind_host: str = os.environ.get("COMPASS_BIND_HOST", "127.0.0.1")
    public_mode: bool = _bool("COMPASS_PUBLIC_MODE", False)
    demo_mode: bool = _bool("COMPASS_DEMO_MODE", False)

    work_hours_start: int = _int("COMPASS_WORK_HOURS_START", 9)
    work_hours_end: int = _int("COMPASS_WORK_HOURS_END", 18)

    # --- College OS (see college-os/) ---------------------------------------
    # Names the Apps Script provisioner created. Override if you renamed them.
    college_root_folder: str = os.environ.get("COMPASS_COLLEGE_ROOT_FOLDER", "COLLEGE")
    college_dashboard_name: str = os.environ.get("COMPASS_COLLEGE_DASHBOARD_NAME", "COLLEGE DASHBOARD")
    # Dashboard CELL CONTENT is never written to the tool cache (it is file
    # content). This is a short in-process memo instead, so one page render
    # doesn't re-read five tabs from the provider.
    college_dashboard_memo_seconds: int = max(
        0, min(_int("COMPASS_COLLEGE_DASHBOARD_MEMO_SECONDS", 300), 3600))

    db_path: Path = Path(os.environ.get("COMPASS_DB_PATH", str(REPO_ROOT / "backend" / "compass.db")))

    # Cache TTLs (seconds)
    ttl_model_catalog: int = _int("COMPASS_TTL_MODEL_CATALOG", 24 * 3600)
    ttl_credential_validation: int = _int("COMPASS_TTL_CREDENTIAL_VALIDATION", 5 * 60)
    ttl_drive_files: int = _int("COMPASS_TTL_DRIVE_FILES", 2 * 3600)
    ttl_calendar_events: int = _int("COMPASS_TTL_CALENDAR_EVENTS", 20 * 60)
    ttl_gmail_activity: int = _int("COMPASS_TTL_GMAIL_ACTIVITY", 20 * 60)
    ttl_meet_activity: int = _int("COMPASS_TTL_MEET_ACTIVITY", 30 * 60)
    ttl_github_activity: int = _int("COMPASS_TTL_GITHUB_ACTIVITY", 30 * 60)
    ttl_analytics: int = _int("COMPASS_TTL_ANALYTICS", 15 * 60)
    ttl_dialogue: int = _int("COMPASS_TTL_DIALOGUE", 24 * 3600)

    session_ttl_seconds: int = _int("COMPASS_SESSION_TTL", 30 * 24 * 3600)

    github_repo_limit: int = _int("COMPASS_GITHUB_REPO_LIMIT", 5)

    def allowed_origins(self) -> list[str]:
        origins = {self.frontend_origin, "http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:8000", "http://127.0.0.1:8000"}
        if self.public_mode:
            # Public mode narrows to the explicitly configured origin only.
            origins = {self.frontend_origin}
        return sorted(o for o in origins if o)

    def origin_allowed(self, origin: str) -> bool:
        """Local mode accepts any loopback origin (Vite may pick 5174, 5175, …
        when 5173 is busy); public mode only the configured origin."""
        if origin in self.allowed_origins():
            return True
        if self.public_mode:
            return False
        import re
        return re.match(r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$", origin) is not None


settings = Settings()
