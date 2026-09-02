"""Canvas: read a student's own calendar feed, no institution required.

Why this shape. Canvas has three doors and only one of them fits Compass:

  * Personal access tokens are being closed off. Instructure caps student-role
    tokens at 120 days and lets an institution disable them outright; some
    already have. A connector built on them breaks per-school and mid-semester.
  * OAuth2 needs a developer key issued by the institution's Canvas admin.
    Instructure's own docs: "You cannot write an application that can be used
    without the institution's permission." That is a connector platform, which
    is precisely what Compass refuses to be.
  * The calendar feed is a personal .ics URL any student can copy from Canvas
    Calendar -> Calendar Feed. No token, no admin, no expiry, no approval.

So Compass reads the feed. That yields deadlines, not evidence: the feed has no
submission status and no grades, so a Canvas assignment can seed a quest but can
never verify one. Verification still comes from Drive, Gmail, Calendar or
GitHub, and `public_link` says so rather than implying otherwise.

The feed URL is a bearer secret — anyone holding it can read the student's
schedule — so it lives in the same encrypted credential store as every other
provider and is masked everywhere it is shown.
"""
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from .. import cache, db, ics
from ..errors import ApiError, ProviderError, not_found
from ..util import new_id, now_iso

logger = logging.getLogger("compass.canvas")

PROVIDER = "canvas"
CONNECTOR = "canvas"

_client: httpx.AsyncClient | None = None


class CanvasError(ProviderError):
    """Safe, redacted Canvas feed failure."""


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
    return _client


async def aclose() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def normalise_url(raw: str) -> str:
    """Accept what a student actually pastes; reject what cannot be a feed."""
    url = (raw or "").strip()
    if url.startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ApiError(422, "invalid_request",
                       "That does not look like a calendar feed URL. In Canvas open "
                       "Calendar, click Calendar Feed, and copy the link it shows.")
    # The feed URL is a bearer secret, so it is upgraded to https — except on
    # loopback, where the request never leaves the machine and a local fixture
    # feed is how this connector is exercised without a real Canvas account.
    if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        url = url.replace("http://", "https://", 1)
    return url


def mask(url: str) -> str:
    """Show enough to recognise the feed, never enough to use it."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return "…"
    return f"{parsed.netloc}/…"


async def fetch(url: str) -> str:
    try:
        resp = await client().get(url, headers={"Accept": "text/calendar, text/plain"})
    except httpx.HTTPError as exc:
        logger.warning("[canvas] feed unreachable: %s", type(exc).__name__)
        raise CanvasError("canvas_unreachable", "Could not reach the Canvas feed.") from exc
    if resp.status_code in (401, 403):
        raise CanvasError("canvas_forbidden",
                          "Canvas refused that feed URL. It may have been reset — copy a fresh "
                          "one from Calendar → Calendar Feed.")
    if resp.status_code == 404:
        raise CanvasError("canvas_not_found", "That feed URL no longer exists in Canvas.")
    if resp.status_code >= 400:
        raise CanvasError("canvas_error", f"Canvas returned {resp.status_code}.")
    body = resp.text
    if "BEGIN:VCALENDAR" not in body:
        raise CanvasError("canvas_not_a_feed",
                          "That URL did not return a calendar. Make sure it is the Calendar Feed "
                          "link and not the Canvas page you were looking at.")
    return body


async def _credentials(profile_id: str) -> dict:
    from .. import providers as provider_service
    return (await provider_service.credentials(profile_id)).get(PROVIDER) or {}


async def feeds(profile_id: str) -> list[dict]:
    """Every calendar feed this profile reads, Canvas first.

    Canvas is the anchor, but a deadline that lives only in Gradescope, Pearson
    or LabFlow never reaches a Canvas feed unless the instructor put it there.
    Any tool that publishes iCalendar can be added alongside — including a
    personal calendar a student syncs those tools into.

    Credentials written before multi-feed carried a single `feed_url`; those are
    read as one Canvas feed rather than migrated, so a downgrade stays safe.
    """
    creds = await _credentials(profile_id)
    stored = creds.get("feeds")
    if isinstance(stored, list):
        return [f for f in stored if f.get("url")]
    if creds.get("feed_url"):
        return [{"id": "canvas", "url": creds["feed_url"], "label": "Canvas", "kind": "canvas"}]
    return []


async def _save_feeds(profile_id: str, items: list[dict]) -> None:
    from .. import providers as provider_service
    await provider_service.save_credentials(profile_id, PROVIDER, {"feeds": items})


async def link(profile_id: str, raw_url: str, *, label: str = "", kind: str = "canvas") -> dict:
    """Verify a feed parses before storing it, so a bad paste fails loudly."""
    url = normalise_url(raw_url)
    kind = "canvas" if kind == "canvas" else "generic"
    body = await fetch(url)
    items = ics.assignments(body, canvas_only=(kind == "canvas"))
    if kind == "canvas" and not items and ics.assignments(body, canvas_only=False):
        raise CanvasError(
            "canvas_no_assignments",
            "That feed parsed but holds no Canvas assignments. If it is a calendar from "
            "another tool, add it as an other feed instead.")

    current = await feeds(profile_id)
    existing = next((f for f in current if f["url"] == url), None)
    if existing:
        existing.update({"label": label.strip()[:60] or existing.get("label") or "Canvas",
                         "kind": kind})
    else:
        current.append({
            "id": new_id(),
            "url": url,
            "label": label.strip()[:60] or ("Canvas" if kind == "canvas" else "Other feed"),
            "kind": kind,
        })
    await _save_feeds(profile_id, current)
    await _mark(profile_id, "ok", None)
    await cache.invalidate_connector(profile_id, CONNECTOR)
    return {"linked": True, "assignment_count": len(items), "feed": mask(url),
            "feed_count": len(current)}


async def unlink_feed(profile_id: str, feed_id: str) -> dict:
    """Remove one feed. Removing the last one clears the credential entirely."""
    current = await feeds(profile_id)
    remaining = [f for f in current if f.get("id") != feed_id]
    if len(remaining) == len(current):
        raise not_found("feed")
    if remaining:
        await _save_feeds(profile_id, remaining)
    else:
        from .. import providers as provider_service
        await provider_service.delete_credentials(profile_id, PROVIDER)
    await cache.invalidate_connector(profile_id, CONNECTOR)
    return {"linked": bool(remaining), "feed_count": len(remaining)}


async def unlink(profile_id: str) -> dict:
    from .. import providers as provider_service
    await provider_service.delete_credentials(profile_id, PROVIDER)
    await cache.invalidate_connector(profile_id, CONNECTOR)
    return {"linked": False}


async def _mark(profile_id: str, status: str, error_code: str | None) -> None:
    await db.get().execute(
        """UPDATE provider_credentials SET status = ?, error_code = ?, last_checked_at = ?
           WHERE profile_id = ? AND provider = ?""",
        (status, error_code, now_iso(), profile_id, PROVIDER))
    await db.get().commit()


async def public_link(profile_id: str) -> dict:
    current = await feeds(profile_id)
    if not current:
        return {"status": "not_linked", "feed": None, "feeds": [], "evidence": False}
    cur = await db.get().execute(
        "SELECT status, error_code, last_checked_at FROM provider_credentials "
        "WHERE profile_id = ? AND provider = ?", (profile_id, PROVIDER))
    row = await cur.fetchone()
    return {
        "status": "linked",
        "feed": mask(current[0]["url"]),
        "feeds": [{"id": f.get("id"), "label": f.get("label"), "kind": f.get("kind", "canvas"),
                   "feed": mask(f["url"])} for f in current],
        "connection_status": (row["status"] if row else "unknown"),
        "error_code": (row["error_code"] if row else None),
        "last_checked_at": (row["last_checked_at"] if row else None),
        # Stated, not implied: this connector cannot close a subgoal.
        "evidence": False,
        "evidence_note": "Canvas feeds carry due dates only — no submissions and no grades — "
                         "so an assignment can start a quest but cannot verify one.",
    }


async def _all_assignments(profile_id: str, *, force: bool = False) -> tuple[list[dict], dict]:
    """Every dated entry across every linked feed, cached. No date window."""
    current = await feeds(profile_id)
    if not current:
        raise ApiError(409, "canvas_not_linked",
                       "No calendar feed linked yet. Add one in Settings → Connections.")

    async def load() -> dict:
        merged: dict[str, dict] = {}
        errors: list[dict] = []
        for feed in current:
            try:
                body = await fetch(feed["url"])
            except CanvasError as exc:
                # One dead feed must not blank out the others: report it and
                # keep whatever the rest still hold.
                errors.append({"feed_id": feed.get("id"), "label": feed.get("label"),
                               "code": exc.code, "message": str(exc)})
                continue
            for item in ics.assignments(body, canvas_only=feed.get("kind", "canvas") == "canvas"):
                item["feed_id"] = feed.get("id")
                item["feed_label"] = feed.get("label")
                # The same assignment reaching Compass through two feeds is one
                # deadline, not two; first feed listed wins.
                merged.setdefault(item["uid"], item)
        items = sorted(merged.values(), key=lambda a: a["due_at"])
        return {"items": items, "errors": errors, "fetched_at": now_iso()}

    payload, meta = await cache.get_or_compute(
        profile_id, "canvas.assignments",
        {"feeds": [mask(f["url"]) for f in current]}, 1800, load, force=force)

    errors = payload.get("errors") or []
    if errors and not payload.get("items"):
        await _mark(profile_id, "error", errors[0]["code"])
    else:
        await _mark(profile_id, "ok", None)
    meta = {**meta, "feed_errors": errors}
    return payload.get("items", []), meta


async def assignments(profile: dict, *, force: bool = False, days: int = 60) -> dict:
    """Upcoming Canvas assignments, windowed for display."""
    items, meta = await _all_assignments(profile["id"], force=force)
    ahead = ics.upcoming(items, now=datetime.now(timezone.utc), days=days)
    return {"items": ahead, "total": len(items), "horizon_days": days, "meta": meta}


def quest_seed(assignment: dict) -> dict:
    """Shape one assignment into the body `create_quest` already accepts.

    Only manual confirmation is offered: a Canvas due date says an assignment
    exists, never that it was handed in. Connecting Drive or GitHub is what
    upgrades these steps to verifiable ones.
    """
    due = assignment.get("due_at") or ""
    goal = assignment["title"]
    if assignment.get("course"):
        goal = f"{assignment['title']} — {assignment['course']}"
    return {
        "goal": goal[:200],
        "meaning": (f"Due {due[:10]} in {assignment['course']}."
                    if assignment.get("course") else f"Due {due[:10]}."),
        "target_date": due[:10] or None,
        "category": "coursework",
        "source": "canvas",
        "source_key": assignment["uid"],
        "document": assignment.get("description") or None,
    }


async def _imports(profile_id: str) -> dict[str, dict]:
    cur = await db.get().execute(
        "SELECT source_key, quest_id FROM canvas_imports WHERE profile_id = ?", (profile_id,))
    return {r["source_key"]: dict(r) for r in await cur.fetchall()}


async def import_assignments(profile: dict, source_keys: list[str], plan: bool = True) -> dict:
    """Create quests from Canvas assignments, idempotently by assignment UID.

    Re-reads the feed server-side so an imported quest matches what Canvas
    actually says, and never double-creates when a student taps twice.
    """
    from . import quests as quest_service

    if not source_keys:
        raise ApiError(422, "invalid_request", "Select at least one assignment to import.")
    items, _ = await _all_assignments(profile["id"])
    by_uid = {a["uid"]: a for a in items}
    already = await _imports(profile["id"])

    created, skipped, unknown = [], [], []
    for uid in source_keys[:20]:
        if uid in already and already[uid].get("quest_id"):
            skipped.append({"source_key": uid, "quest_id": already[uid]["quest_id"]})
            continue
        assignment = by_uid.get(uid)
        if assignment is None:
            unknown.append(uid)
            continue
        seed = quest_seed(assignment)
        document = seed.pop("document", None)
        if document and plan:
            # The assignment text is a brief the student already has, so plan
            # from it rather than inventing a breakdown.
            quest = await quest_service.create_quest_from_document(
                profile["id"], seed["goal"], document,
                {"target_date": seed["target_date"], "category": seed["category"]})
        else:
            quest = await quest_service.create_quest(profile["id"], {
                "goal": seed["goal"], "meaning": seed["meaning"],
                "target_date": seed["target_date"], "plan": plan,
            })
        await db.get().execute(
            """INSERT INTO canvas_imports (profile_id, source_key, title, course, due_at,
                                           quest_id, imported_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(profile_id, source_key) DO UPDATE SET
                 quest_id = excluded.quest_id, imported_at = excluded.imported_at""",
            (profile["id"], uid, assignment["title"][:200], assignment.get("course"),
             assignment.get("due_at"), quest["id"], now_iso()))
        await db.get().commit()
        created.append({"source_key": uid, "quest_id": quest["id"], "goal": quest["goal"]})

    return {"created": created, "skipped": skipped, "unknown": unknown}


async def overview(profile: dict, force: bool = False) -> dict:
    """Everything the Canvas panel needs in one call."""
    link = await public_link(profile["id"])
    if link["status"] != "linked":
        return {"link": link, "assignments": [], "imports": []}
    try:
        data = await assignments(profile, force=force)
        items, meta, error = data["items"], data["meta"], None
    except ProviderError as exc:
        items, meta, error = [], {}, {"code": exc.code, "message": str(exc)}
    feed_errors = (meta or {}).get("feed_errors") or []
    already = await _imports(profile["id"])
    for a in items:
        a["imported_quest_id"] = already.get(a["uid"], {}).get("quest_id")
    return {"link": link, "assignments": items, "imports": list(already.values()),
            "meta": meta, "error": error, "feed_errors": feed_errors}
