"""Direct GitHub REST client — how Compass sees code work.

A fine-grained personal access token with read-only repository access is enough,
and GitHub charges nothing for it. Responses are normalised to the same shapes
the rest of Compass parses.

Read-only by construction, same as everything else: only GET is ever issued.
"""
import asyncio
import logging

import httpx

from .errors import ProviderError

logger = logging.getLogger("compass.github")

API_BASE = "https://api.github.com"

_semaphore = asyncio.Semaphore(3)
_client: httpx.AsyncClient | None = None


class GitHubError(ProviderError):
    """Safe, redacted GitHub failure."""


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(base_url=API_BASE, timeout=30.0)
    return _client


async def aclose() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _get(token: str, path: str, params: dict | None = None) -> object:
    if not token:
        raise GitHubError("github_not_configured", "No GitHub token is configured.")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    async with _semaphore:
        try:
            resp = await client().get(path, params=params or {}, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("[github] transport error on %s: %s", path, type(exc).__name__)
            raise GitHubError("github_unreachable", "Could not reach GitHub.") from exc
    if resp.status_code == 401:
        raise GitHubError("github_unauthorized", "GitHub rejected the token.")
    if resp.status_code == 403 and "rate limit" in resp.text.lower():
        raise GitHubError("github_rate_limited", "GitHub rate limit reached; try again later.")
    if resp.status_code >= 400:
        logger.warning("[github] %s returned %s", path, resp.status_code)
        raise GitHubError(f"github_http_{resp.status_code}", f"GitHub returned {resp.status_code}.")
    try:
        return resp.json()
    except ValueError as exc:
        raise GitHubError("github_bad_response", "GitHub returned an unreadable response.") from exc


# ------------------------------------------------------------- capabilities

async def validate(token: str) -> dict:
    user = await _get(token, "/user")
    login = user.get("login") if isinstance(user, dict) else None
    return {"success": bool(login), "message": "ok" if login else "no user"}


async def get_repositories(token: str, arguments: dict) -> dict:
    filters = arguments.get("filter") or {}
    pagination = arguments.get("pagination") or {}
    repos = await _get(token, "/user/repos", {
        "type": filters.get("type") or "owner",
        "sort": filters.get("sort") or "pushed",
        "direction": filters.get("direction") or "desc",
        "per_page": min(int(pagination.get("per_page") or 30), 100),
        "page": int(pagination.get("page") or 1),
    })
    return {"repositories": [{"full_name": r.get("full_name"), "private": r.get("private")}
                             for r in repos or [] if isinstance(r, dict)]}


async def get_commits(token: str, arguments: dict) -> dict:
    owner, repo = arguments.get("owner"), arguments.get("repo")
    if not owner or not repo:
        raise GitHubError("github_bad_request", "owner and repo are required.")
    pagination = arguments.get("pagination") or {}
    params = {"per_page": min(int(pagination.get("per_page") or 100), 100),
              "page": int(pagination.get("page") or 1)}
    if arguments.get("since"):
        params["since"] = arguments["since"]
    if arguments.get("author"):
        params["author"] = arguments["author"]
    try:
        commits = await _get(token, f"/repos/{owner}/{repo}/commits", params)
    except GitHubError as exc:
        # An empty repository answers 409 — that is not a failure worth raising.
        if exc.code == "github_http_409":
            return {"commits": []}
        raise
    return {"commits": [
        {"sha": c.get("sha"),
         "message": (c.get("commit") or {}).get("message") or "",
         "commit": c.get("commit") or {},
         "created_at": ((c.get("commit") or {}).get("author") or {}).get("date")}
        for c in commits or [] if isinstance(c, dict)]}


async def get_pull_requests(token: str, arguments: dict) -> dict:
    owner, repo = arguments.get("owner"), arguments.get("repo")
    if not owner or not repo:
        raise GitHubError("github_bad_request", "owner and repo are required.")
    filters = arguments.get("filter") or {}
    pagination = arguments.get("pagination") or {}
    prs = await _get(token, f"/repos/{owner}/{repo}/pulls", {
        "state": filters.get("state") or "all",
        "sort": filters.get("sort") or "created",
        "direction": filters.get("direction") or "desc",
        "per_page": min(int(pagination.get("per_page") or 50), 100),
        "page": int(pagination.get("page") or 1),
    })
    return {"pull_requests": [
        {"number": p.get("number"), "title": p.get("title") or "", "state": p.get("state"),
         # The list endpoint omits `merged`; merged_at is the same fact.
         "merged": bool(p.get("merged_at")),
         "created_at": p.get("created_at"), "merged_at": p.get("merged_at")}
        for p in prs or [] if isinstance(p, dict)]}


CAPABILITIES = {
    "github.get_repositories": get_repositories,
    "github.get_commits": get_commits,
    "github.get_pull_requests": get_pull_requests,
}


async def call(token: str, capability: str, arguments: dict) -> dict:
    if capability == "github.validate":
        return await validate(token)
    handler = CAPABILITIES.get(capability)
    if handler is None:
        raise GitHubError("capability_unsupported", f"GitHub cannot serve {capability}.")
    return await handler(token, arguments)
