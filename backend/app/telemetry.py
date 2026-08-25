"""Bounded provider adapters, telemetry snapshots, and deterministic evidence
extraction.

All reads go through logical capabilities resolved by the registry (read-only
allowlist). Raw document/sheet/slide content is fetched WITHOUT persistent
caching — excerpts live in process memory only; snapshots store hashes and
counts, never bodies.
"""
import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone

from . import cache, capabilities, providers
from .config import settings
from .errors import ApiError
from .util import new_id, now, now_iso, parse_iso, sha256_hex

logger = logging.getLogger("compass.telemetry")

GOOGLE_DOC = "application/vnd.google-apps.document"
GOOGLE_SHEET = "application/vnd.google-apps.spreadsheet"
GOOGLE_SLIDE = "application/vnd.google-apps.presentation"
WORKSPACE_MIMES = {GOOGLE_DOC, GOOGLE_SHEET, GOOGLE_SLIDE}

_MAX_PAGES = 3


def _registry() -> capabilities.CapabilityRegistry:
    reg = capabilities.current_registry()
    if reg is None:
        raise ApiError(503, "capabilities_unavailable", "Capabilities not discovered yet.")
    return reg


async def call_capability(profile: dict, capability: str, arguments: dict,
                          ttl_seconds: int | None = None, force: bool = False,
                          connector: str | None = None, serve_stale_on_error: bool = False) -> tuple[dict, dict]:
    """Resolve an allowlisted logical capability and call it for this profile's
    own connected account, through the profile-scoped cache.

    How it is answered — the Apps Script bridge or the GitHub client — is
    decided in `providers`; nothing here depends on it."""
    reg = _registry()
    if reg.resolve(capability) is None:
        raise ApiError(503, "capability_unsupported", f"Capability {capability} is not available.")
    connector = connector or capability.split(".", 1)[0]

    async def fetch():
        return await providers.call(profile, capability, arguments)

    if ttl_seconds is None:
        # Uncached direct call (used only for raw content that must not persist).
        return await fetch(), {"from_cache": False, "stale": False}
    return await cache.get_or_fetch(
        scope_id=profile["id"], connector=connector, capability=capability,
        arguments=arguments, ttl_seconds=ttl_seconds, fetch_fn=fetch, force=force,
        serve_stale_on_error=serve_stale_on_error,
    )


# ------------------------------------------------------------- bucketing

def _bucket_day(dt: datetime) -> str:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _bucket_hour(dt: datetime) -> str:
    return dt.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------- drive

async def list_drive_files(profile: dict, force: bool = False,
                           serve_stale_on_error: bool = False) -> tuple[list[dict], dict]:
    arguments = {"page_size": 1000}
    if settings.drive_owned_only:
        arguments["owned_only"] = True

    async def _fetch_pages():
        files: list[dict] = []
        page_token = None
        for _ in range(_MAX_PAGES):
            args = dict(arguments)
            if page_token:
                args["page_token"] = page_token
            payload = await providers.call(profile, "drive.list_files", args)
            files.extend(payload.get("files") or [])
            page_token = payload.get("next_page_token")
            if not page_token:
                break
        return {"files": files}

    reg = _registry()
    if reg.resolve("drive.list_files") is None:
        raise ApiError(503, "capability_unsupported", "Drive listing is not available.")
    payload, meta = await cache.get_or_fetch(
        scope_id=profile["id"], connector="google_drive", capability="drive.list_files",
        arguments=arguments, ttl_seconds=settings.ttl_drive_files, fetch_fn=_fetch_pages,
        force=force, serve_stale_on_error=serve_stale_on_error,
    )
    return payload.get("files") or [], meta


async def search_recent_workspace_files(profile: dict, limit: int = 60, days: int = 90,
                                        force: bool = False) -> tuple[list[dict], dict]:
    """At most `limit` recent, non-trashed native Workspace files."""
    files, meta = await list_drive_files(profile, force=force)
    cutoff = now() - timedelta(days=days)
    picked = []
    for f in files:
        if f.get("trashed"):
            continue
        if f.get("mime_type") not in WORKSPACE_MIMES:
            continue
        ts = f.get("modified_time")
        try:
            if not ts or parse_iso(ts) < cutoff:
                continue
        except ValueError:
            continue
        picked.append(f)
    picked.sort(key=lambda f: f.get("modified_time") or "", reverse=True)
    return picked[:limit], meta


# ------------------------------------------------------- content excerpts
# In-memory only. Never cached, never logged, never persisted.

_WS = re.compile(r"\s+")


def _normalize(text: str, cap: int = 4000) -> str:
    return _WS.sub(" ", text or "").strip()[:cap]


def _walk_strings(node, out: list[str], cap: int) -> None:
    if len(out) >= cap:
        return
    if isinstance(node, str):
        s = node.strip()
        if 2 < len(s) < 500:
            out.append(s)
    elif isinstance(node, dict):
        for v in node.values():
            _walk_strings(v, out, cap)
    elif isinstance(node, list):
        for v in node:
            _walk_strings(v, out, cap)


async def summarize_document(profile: dict, file_ref: dict, cap: int = 4000) -> str | None:
    reg = _registry()
    if reg.resolve("docs.get_text") is None:
        return None
    try:
        payload, _ = await call_capability(profile, "docs.get_text",
                                           {"document_id": file_ref["id"]}, ttl_seconds=None)
    except Exception:
        return None
    text = payload.get("text") if isinstance(payload, dict) else None
    if not text and isinstance(payload, dict):
        parts: list[str] = []
        _walk_strings(payload, parts, 500)
        text = " ".join(parts)
    return _normalize(text or "", cap) or None


async def summarize_sheet(profile: dict, file_ref: dict, cap: int = 4000) -> str | None:
    reg = _registry()
    cap_name = "sheets.get_values" if reg.resolve("sheets.get_values") else None
    if cap_name is None:
        return None
    try:
        payload, _ = await call_capability(profile, cap_name,
                                           {"spreadsheet_id": file_ref["id"]}, ttl_seconds=None)
    except Exception:
        return None
    cells: list[str] = []
    _walk_strings(payload, cells, 200)  # at most 200 non-empty cells
    return _normalize(" | ".join(cells), cap) or None


async def summarize_presentation(profile: dict, file_ref: dict, cap: int = 4000) -> str | None:
    reg = _registry()
    if reg.resolve("slides.get_presentation") is None:
        return None
    try:
        payload, _ = await call_capability(profile, "slides.get_presentation",
                                           {"presentation_id": file_ref["id"]}, ttl_seconds=None)
    except Exception:
        return None
    texts: list[str] = []
    _walk_strings(payload, texts, 40)  # titles + at most 40 text elements
    return _normalize(" | ".join(texts), cap) or None


# ------------------------------------------------------------- providers

async def calendar_activity(profile: dict, start: datetime, end: datetime,
                            force: bool = False, serve_stale_on_error: bool = False) -> tuple[list[dict], dict]:
    time_min, time_max = _bucket_day(start), _bucket_day(end + timedelta(days=1))
    arguments = {"calendar_id": "primary", "max_results": 2500, "time_min": time_min,
                 "time_max": time_max, "single_events": True, "order_by": "startTime"}
    payload, meta = await call_capability(
        profile, "calendar.list_events", arguments,
        ttl_seconds=settings.ttl_calendar_events, force=force, serve_stale_on_error=serve_stale_on_error)
    return ((payload.get("events") or {}).get("items")) or [], meta


async def sent_email_evidence(profile: dict, start: datetime, force: bool = False) -> tuple[dict, dict]:
    after = _bucket_hour(start)
    epoch = int(parse_iso(after).timestamp())
    arguments = {"q": f"in:sent after:{epoch}", "maxResults": 25}

    async def fetch():
        payload = await providers.call(profile, "gmail.list_messages", arguments)
        refs = payload.get("messages") or []
        return {"ids": [r.get("id") for r in refs if r.get("id")],
                "estimate": payload.get("result_size_estimate") or len(refs)}

    if _registry().resolve("gmail.list_messages") is None:
        raise ApiError(503, "capability_unsupported", "Gmail is not available.")
    return await cache.get_or_fetch(
        scope_id=profile["id"], connector="gmail", capability="gmail.sent_since",
        arguments=arguments, ttl_seconds=settings.ttl_gmail_activity, fetch_fn=fetch, force=force)


async def github_activity(profile: dict, since: datetime, force: bool = False,
                          serve_stale_on_error: bool = False) -> tuple[dict, dict]:
    since_iso = _bucket_hour(since)

    async def fetch():
        reg = _registry()
        repos_payload = await providers.call(profile, "github.get_repositories", {
            "filter": {"type": "owner", "sort": "pushed", "direction": "desc"},
            "pagination": {"per_page": settings.github_repo_limit},
        }) if reg.resolve("github.get_repositories") else {}
        repos = [r["full_name"] for r in (repos_payload.get("repositories") or []) if r.get("full_name")]
        commits, prs = [], []
        for full_name in repos[: settings.github_repo_limit]:
            owner, _, repo = full_name.partition("/")
            if not repo:
                continue
            if reg.resolve("github.get_commits"):
                p = await providers.call(profile, "github.get_commits", {
                    "owner": owner, "repo": repo, "since": since_iso,
                    "pagination": {"page": 1, "per_page": 100}})
                for c in p.get("commits") or []:
                    created = c.get("created_at") or ((c.get("commit") or {}).get("author") or {}).get("date")
                    commits.append({"sha": c.get("sha"), "message": (c.get("commit") or {}).get("message")
                                    or c.get("message") or "", "created_at": created, "repo": full_name})
            if reg.resolve("github.get_pull_requests"):
                p = await providers.call(profile, "github.get_pull_requests", {
                    "owner": owner, "repo": repo,
                    "filter": {"state": "all", "sort": "created", "direction": "desc"},
                    "pagination": {"page": 1, "per_page": 50}})
                for pr in p.get("pull_requests") or []:
                    prs.append({"number": pr.get("number"), "title": pr.get("title") or "",
                                "state": pr.get("state"), "merged": pr.get("merged"),
                                "created_at": pr.get("created_at"), "merged_at": pr.get("merged_at"),
                                "repo": full_name})
        return {"repos": repos, "commits": commits, "pull_requests": prs}

    if _registry().resolve("github.get_repositories") is None:
        raise ApiError(503, "capability_unsupported", "GitHub is not available.")
    return await cache.get_or_fetch(
        scope_id=profile["id"], connector="github", capability="github.activity",
        arguments={"since": since_iso}, ttl_seconds=settings.ttl_github_activity,
        fetch_fn=fetch, force=force, serve_stale_on_error=serve_stale_on_error)


async def meet_activity(profile: dict, since: datetime, force: bool = False,
                        serve_stale_on_error: bool = False) -> tuple[list[dict], dict]:
    filter_str = f'startTime>="{_bucket_hour(since)}"'
    arguments = {"filter": filter_str, "page_size": 100}
    payload, meta = await call_capability(
        profile, "meet.list_conference_records", arguments,
        ttl_seconds=settings.ttl_meet_activity, force=force, connector="google_meet",
        serve_stale_on_error=serve_stale_on_error)
    return payload.get("conference_records") or [], meta


# --------------------------------------------------------------- snapshots

def specs_to_connectors(evidence_specs: list[str]) -> set[str]:
    from .llm import EVIDENCE_CONNECTOR
    return {EVIDENCE_CONNECTOR[s] for s in evidence_specs
            if s in EVIDENCE_CONNECTOR and EVIDENCE_CONNECTOR[s] != "manual"}


async def capture_snapshot(profile: dict, evidence_specs: list[str], phase: str,
                           session_id: str | None, window_start: datetime | None = None) -> dict:
    """Normalized metrics for the connectors these specs need.

    phase='baseline' uses cached telemetry only (no forced provider call);
    phase='final' refreshes each required provider once.
    """
    from . import db
    force = phase == "final"
    connectors = specs_to_connectors(evidence_specs)
    window_start = window_start or (now() - timedelta(hours=24))
    metrics: dict = {}
    generations: dict = {}

    drive_needed = connectors & {"google_drive", "google_docs", "google_sheets", "google_slides"}
    if drive_needed:
        try:
            files, _ = await search_recent_workspace_files(profile, force=force)
            metrics["files"] = {
                f["id"]: {"name": f.get("name"), "mime_type": f.get("mime_type"),
                          "modified_time": f.get("modified_time"), "created_time": f.get("created_time")}
                for f in files if f.get("id")
            }
        except Exception as exc:
            metrics["files_error"] = getattr(exc, "code", type(exc).__name__)
    if "gmail" in connectors:
        try:
            sent, _ = await sent_email_evidence(profile, window_start, force=force)
            metrics["sent_email"] = sent
        except Exception as exc:
            metrics["gmail_error"] = getattr(exc, "code", type(exc).__name__)
    if "google_calendar" in connectors:
        try:
            evs, _ = await calendar_activity(profile, window_start, now() + timedelta(days=1), force=force)
            metrics["calendar_events"] = [
                {"id": e.get("id"), "summary": e.get("summary"),
                 "start": (e.get("start") or {}).get("date_time"),
                 "end": (e.get("end") or {}).get("date_time")}
                for e in evs][:100]
        except Exception as exc:
            metrics["calendar_error"] = getattr(exc, "code", type(exc).__name__)
    if "github" in connectors:
        try:
            gh, _ = await github_activity(profile, window_start, force=force)
            metrics["github"] = {
                "commits": {c["sha"]: {"message": (c.get("message") or "")[:120], "repo": c["repo"],
                                       "created_at": c.get("created_at")}
                            for c in gh.get("commits") or [] if c.get("sha")},
                "prs": {f"{p['repo']}#{p['number']}": {"title": (p.get("title") or "")[:120],
                                                       "state": p.get("state"), "merged": bool(p.get("merged")),
                                                       "created_at": p.get("created_at")}
                        for p in gh.get("pull_requests") or [] if p.get("number") is not None},
            }
        except Exception as exc:
            metrics["github_error"] = getattr(exc, "code", type(exc).__name__)
    if "google_meet" in connectors:
        try:
            records, _ = await meet_activity(profile, window_start, force=force)
            metrics["meet_records"] = [
                {"id": r.get("name") or r.get("id"), "start_time": r.get("start_time"),
                 "end_time": r.get("end_time")}
                for r in records][:50]
        except Exception as exc:
            metrics["meet_error"] = getattr(exc, "code", type(exc).__name__)

    for connector in connectors:
        generations[connector] = await cache.connector_generation(profile["id"], connector)

    snapshot_id = new_id()
    import json as _json
    await db.get().execute(
        "INSERT INTO telemetry_snapshots (id, profile_id, session_id, phase, metrics_json, generations_json, captured_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (snapshot_id, profile["id"], session_id, phase, _json.dumps(metrics),
         _json.dumps(generations), now_iso()))
    await db.get().commit()
    return {"id": snapshot_id, "phase": phase, "metrics": metrics, "generations": generations,
            "captured_at": now_iso()}


# --------------------------------------------------------------- evidence

def _ref_hash(value: str) -> str:
    return sha256_hex(f"evidence::{value}")[:16]


def extract_evidence(baseline: dict, final: dict, evidence_specs: list[str],
                     session_window: tuple[str, str] | None = None) -> list[dict]:
    """Deterministic diff of two snapshots into evidence items (plain dicts)."""
    b, f = baseline.get("metrics", {}), final.get("metrics", {})
    items: list[dict] = []

    def add(source: str, event_type: str, summary: str, ref: str,
            occurred_at: str | None = None, delta: dict | None = None):
        items.append({
            "source": source, "event_type": event_type, "summary": summary[:200],
            "external_ref_hash": _ref_hash(ref), "content_hash": None,
            "occurred_at": occurred_at, "metric_delta": delta or {},
        })

    b_files, f_files = b.get("files") or {}, f.get("files") or {}
    mime_spec = {GOOGLE_DOC: "document_content_changed", GOOGLE_SHEET: "sheet_values_changed",
                 GOOGLE_SLIDE: "presentation_content_changed"}
    content_source = {"document_content_changed": "google_docs",
                      "sheet_values_changed": "google_sheets",
                      "presentation_content_changed": "google_slides"}
    for fid, info in f_files.items():
        name = info.get("name") or "a file"
        if fid not in b_files:
            if "file_created" in evidence_specs:
                add("google_drive", "file_created", f"New file created: {name}", fid,
                    info.get("created_time"))
            content_spec = mime_spec.get(info.get("mime_type"))
            if content_spec and content_spec in evidence_specs:
                add(content_source[content_spec], content_spec, f"New content in: {name}", fid,
                    info.get("modified_time"))
                # transient plain ref so verification can fetch a bounded
                # excerpt; never persisted (only the hash is stored)
                items[-1]["_ref"] = fid
            continue
        if info.get("modified_time") != b_files[fid].get("modified_time"):
            if "file_modified" in evidence_specs:
                add("google_drive", "file_modified", f"File modified: {name}", fid, info.get("modified_time"))
            content_spec = mime_spec.get(info.get("mime_type"))
            if content_spec and content_spec in evidence_specs:
                add(content_source[content_spec], content_spec, f"Content changed in: {name}", fid,
                    info.get("modified_time"),
                    {"modified_from": b_files[fid].get("modified_time"),
                     "modified_to": info.get("modified_time")})
                items[-1]["_ref"] = fid

    if "email_sent" in evidence_specs:
        b_ids = set((b.get("sent_email") or {}).get("ids") or [])
        f_ids = (f.get("sent_email") or {}).get("ids") or []
        new_ids = [i for i in f_ids if i not in b_ids]
        for mid in new_ids[:10]:
            add("gmail", "email_sent", "A relevant email was sent from your account.", mid)

    if "calendar_event_completed" in evidence_specs and session_window:
        ws, we = session_window
        for e in f.get("calendar_events") or []:
            end_ts = e.get("end")
            if end_ts and ws <= end_ts <= we:
                add("google_calendar", "calendar_event_completed",
                    f"Calendar block ended during the session: {e.get('summary') or 'event'}",
                    e.get("id") or "", end_ts)

    gh_b, gh_f = b.get("github") or {}, f.get("github") or {}
    if "github_commit_created" in evidence_specs:
        for sha, info in (gh_f.get("commits") or {}).items():
            if sha not in (gh_b.get("commits") or {}):
                add("github", "github_commit_created",
                    f"New commit in {info.get('repo')}: {info.get('message', '')[:80]}", sha,
                    info.get("created_at"))
    if "github_pull_request_opened" in evidence_specs:
        for key, info in (gh_f.get("prs") or {}).items():
            if key not in (gh_b.get("prs") or {}):
                add("github", "github_pull_request_opened",
                    f"PR opened in {key.split('#')[0]}: {info.get('title', '')[:80]}", key,
                    info.get("created_at"))
    if "github_pull_request_merged" in evidence_specs:
        for key, info in (gh_f.get("prs") or {}).items():
            was = (gh_b.get("prs") or {}).get(key)
            if info.get("merged") and (was is None or not was.get("merged")):
                add("github", "github_pull_request_merged",
                    f"PR merged in {key.split('#')[0]}: {info.get('title', '')[:80]}", f"{key}:merged")

    if "meet_attended" in evidence_specs:
        b_ids = {r.get("id") for r in b.get("meet_records") or []}
        for r in f.get("meet_records") or []:
            if r.get("id") not in b_ids and r.get("start_time"):
                add("google_meet", "meet_attended",
                    "You attended a Google Meet call during this window.", str(r.get("id")),
                    r.get("start_time"),
                    {"start": r.get("start_time"), "end": r.get("end_time")})

    return items


def unavailable_specs(evidence_specs: list[str], baseline: dict, final: dict) -> list[str]:
    """Specs whose provider errored in either snapshot (honest 'could not observe')."""
    from .llm import EVIDENCE_CONNECTOR
    error_keys = {"google_drive": "files_error", "google_docs": "files_error",
                  "google_sheets": "files_error", "google_slides": "files_error",
                  "gmail": "gmail_error", "google_calendar": "calendar_error",
                  "github": "github_error", "google_meet": "meet_error"}
    out = []
    for spec in evidence_specs:
        connector = EVIDENCE_CONNECTOR.get(spec)
        key = error_keys.get(connector or "")
        if key and (key in (baseline.get("metrics") or {}) or key in (final.get("metrics") or {})):
            out.append(spec)
        if spec == "github_checks_passed":
            out.append(spec)  # checks capability is best-effort; mark honestly
    return sorted(set(out))
