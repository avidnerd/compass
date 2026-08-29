import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app import bridge, capabilities, crypto, db, github, jobs, openrouter, providers  # noqa: E402
from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402

BRIDGE_URL = "https://script.google.com/macros/s/AKfycbxTESTDEPLOYMENT/exec"
BRIDGE_TOKEN = "test-bridge-token-0123456789"
GITHUB_TOKEN = "ghp_testtoken0123456789"

FREE_CATALOG = {"data": [
    {"id": "google/gemma-4-26b-a4b-it:free", "name": "Gemma 4 (free)",
     "pricing": {"prompt": "0", "completion": "0"},
     "supported_parameters": ["response_format", "structured_outputs"]},
    {"id": "openai/gpt-oss-20b:free", "name": "GPT-OSS (free)",
     "pricing": {"prompt": "0", "completion": "0"},
     "supported_parameters": ["structured_outputs"]},
    {"id": "nvidia/nemotron-3-super-120b-a12b:free", "name": "Nemotron (free)",
     "pricing": {"prompt": "0", "completion": "0"},
     "supported_parameters": ["structured_outputs"]},
    # Free and zero-priced but does NOT advertise structured outputs — only
    # eligible when explicitly preferred (scan model), never in the default chain.
    {"id": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", "name": "Nemotron Omni (free)",
     "pricing": {"prompt": "0", "completion": "0"},
     "supported_parameters": ["temperature"],
     "architecture": {"input_modalities": ["text", "image"]}},
    {"id": "openrouter/auto", "name": "Auto router",
     "pricing": {"prompt": "-1", "completion": "-1"}, "supported_parameters": []},
    {"id": "openai/gpt-4o", "name": "Paid model",
     "pricing": {"prompt": "0.005", "completion": "0.015"},
     "supported_parameters": ["structured_outputs"]},
]}


class FakeAppsScript:
    """In-memory stand-in for college-os/bridge/api.gs, mutable per test.

    Served through a real httpx MockTransport, so `app.bridge` does its own URL
    validation, token handling, and error mapping on the way through.
    """

    def __init__(self):
        self.files: list[dict] = []
        self.events: list[dict] = []
        self.messages: list[dict] = []
        self.sent_messages: list[dict] = []
        self.doc_texts: dict[str, str] = {}
        self.calendars: list[dict] = []
        # {spreadsheet_id: {tab_name: [[cell, ...], ...]}} — when a spreadsheet
        # is registered here, sheet reads are answered per tab.
        self.sheets: dict[str, dict[str, list[list]]] = {}
        self.calls: list[tuple[str, dict]] = []
        self.serve_sign_in_page = False

    def respond(self, fn: str, args: dict) -> dict:
        self.calls.append((fn, args))
        if fn == "bridge.hello":
            return {"ok": True, "capabilities": ["drive.list_files"], "timezone": "America/New_York"}
        if fn == "drive.list_files":
            return {"files": list(self.files), "next_page_token": None}
        if fn == "docs.get_text":
            return {"text": self.doc_texts.get(args.get("document_id"), "")}
        if fn == "sheets.get_values":
            tabs = self.sheets.get(args.get("spreadsheet_id"))
            if tabs is None:
                return {"values": [["alpha", "beta"], ["gamma", "delta"]]}
            requested = args.get("range") or args.get("sheet_name") or ""
            for name, values in tabs.items():
                if requested.startswith(f"'{name}'!") or requested == name:
                    return {"values": values}
            return {"values": []}
        if fn == "slides.get_presentation":
            return {"slides": [{"title": "Deck title", "elements": ["point one", "point two"]}]}
        if fn == "calendar.list_calendars":
            return {"calendars": list(self.calendars)}
        if fn == "calendar.list_events":
            return {"events": {"items": list(self.events)}}
        if fn == "gmail.list_messages":
            found = self.sent_messages if "in:sent" in (args.get("q") or "") else self.messages
            return {"messages": [{"id": m["id"]} for m in found],
                    "result_size_estimate": len(found)}
        if fn == "gmail.get_message":
            return {"id": args.get("message_id"), "snippet": "hi", "payload": {"headers": []}}
        return {"error": {"code": "capability_unsupported", "message": fn}}

    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            if self.serve_sign_in_page:
                return httpx.Response(200, text="<html>Sign in to continue</html>",
                                      headers={"content-type": "text/html"})
            params = dict(request.url.params)
            if params.get("token") != BRIDGE_TOKEN:
                return httpx.Response(200, json={"error": {"code": "unauthorized"}})
            args = json.loads(params.get("args") or "{}")
            return httpx.Response(200, json=self.respond(params.get("fn", ""), args))
        return httpx.MockTransport(handler)


class FakeGitHub:
    """GitHub's REST API, as far as `app.github` can tell."""

    def __init__(self):
        self.repos: list[dict] = []
        # {full_name: [raw commit, ...]} / {full_name: [raw pull, ...]}
        self.commits: dict[str, list[dict]] = {}
        self.pulls: dict[str, list[dict]] = {}
        self.calls: list[str] = []
        self.unauthorized = False

    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            if self.unauthorized or request.headers.get("authorization") != f"Bearer {GITHUB_TOKEN}":
                return httpx.Response(401, json={"message": "Bad credentials"})
            path = request.url.path
            self.calls.append(path)
            if path == "/user":
                return httpx.Response(200, json={"login": "avidnerd"})
            if path == "/user/repos":
                return httpx.Response(200, json=self.repos)
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[0] == "repos":
                full_name = f"{parts[1]}/{parts[2]}"
                if parts[3] == "commits":
                    return httpx.Response(200, json=self.commits.get(full_name, []))
                if parts[3] == "pulls":
                    return httpx.Response(200, json=self.pulls.get(full_name, []))
            return httpx.Response(404, json={"message": "nope"})
        return httpx.MockTransport(handler)


class FakeLLM:
    """Stands in for openrouter._request_once; enforces the :free invariant."""

    def __init__(self):
        self.requests: list[str] = []
        self.prompts: list[tuple[str, str]] = []  # (schema name, concatenated messages)
        self.fail_models: set[str] = set()
        self.responses: dict[str, dict] = {}

    async def __call__(self, model_id, messages, schema_model, temperature):
        assert model_id.endswith(":free"), f"paid route attempted: {model_id}"
        assert model_id != "openrouter/auto"
        self.requests.append(model_id)
        self.prompts.append((schema_model.__name__,
                             "\n".join(str(m.get("content", "")) for m in messages)))
        if model_id in self.fail_models:
            from app.openrouter import _Transient
            raise _Transient(None)
        name = schema_model.__name__
        if name in self.responses:
            return json.dumps(self.responses[name])
        return json.dumps(_default_response(name))


def _default_response(schema_name: str) -> dict:
    if schema_name == "VerificationDraft":
        return {"completed": True, "confidence": 0.9,
                "explanation": "Evidence clearly shows progress.",
                "observed": "New activity in connected sources.",
                "not_observed": "Nothing else."}
    if schema_name == "QuestPlan":
        sub = {"title": "Draft the outline", "rationale": "Start small",
               "acceptance_criterion": "An outline document exists",
               "estimated_sessions": 1, "difficulty": 2,
               "evidence_types": ["file_created"], "manual_fallback": "Did you draft it?"}
        return {"subgoals": [dict(sub, title=f"Step {i}") for i in range(1, 4)],
                "category": "writing"}
    if schema_name == "InterestProfileDraft":
        return {"themes": [{"label": "Gardening", "confidence": 0.8}],
                "palette": "meadow", "motif": "leaves", "accessories": ["flower"],
                "props": ["terrarium"], "personality_presets": ["cheerful", "gentle", "curious"],
                "name_suggestions": ["Fern", "Moss", "Clover"], "tone": "warm",
                "confidence": 0.7, "explanation": "Lots of plant docs."}
    if schema_name == "ReactionBatch":
        return {"reaction": "We did it!", "encouragement": "Onward!",
                "journal_memory": "A great session together."}
    if schema_name == "BossTheme":
        return {"name": "The Test Boss", "narration": "It looms.", "defeat_line": "It falls."}
    if schema_name == "Postcard":
        return {"text": "Dear friend, what a day."}
    raise AssertionError(f"unknown schema {schema_name}")


@pytest_asyncio.fixture
async def env(tmp_path, monkeypatch):
    """Fully wired test app: a fake Apps Script bridge + GitHub, both adopted
    from the workspace .env defaults, plus a fake free-model gateway."""
    await db.close()
    await db.connect(tmp_path / "test.db")
    await db.run_migrations()

    script, gh, fake_llm = FakeAppsScript(), FakeGitHub(), FakeLLM()

    await bridge.aclose()
    await github.aclose()
    bridge._client = httpx.AsyncClient(transport=script.transport(), follow_redirects=True, timeout=5)
    github._client = httpx.AsyncClient(base_url=github.API_BASE, transport=gh.transport(), timeout=5)

    monkeypatch.setattr(settings, "bridge_url", BRIDGE_URL)
    monkeypatch.setattr(settings, "bridge_token", BRIDGE_TOKEN)
    monkeypatch.setattr(settings, "github_token", GITHUB_TOKEN)
    monkeypatch.setattr(settings, "openrouter_api_key", "test-or-key")
    monkeypatch.setattr(settings, "app_secret", "test-app-secret-for-credential-encryption")
    crypto.reset_cache()

    async def fake_catalog(force=False):
        return FREE_CATALOG
    monkeypatch.setattr(openrouter, "refresh_free_model_catalog", fake_catalog)
    monkeypatch.setattr(openrouter, "_request_once", fake_llm)

    capabilities.set_registry(capabilities.build_bridge_registry(providers.bridge_capabilities()))

    jobs._queue = asyncio.Queue()
    jobs.start_workers()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield type("Env", (), {"client": client, "script": script, "github": gh, "llm": fake_llm})()

    await jobs.stop_workers()
    capabilities.set_registry(None)
    crypto.reset_cache()
    await bridge.aclose()
    await github.aclose()
    await db.close()


@pytest_asyncio.fixture
async def unconfigured(env, monkeypatch):
    """`env` with no provider credentials at all — the first-run state, and the
    starting point for the adoption handshakes. The registry stays installed:
    it describes what this path can serve, not what is connected."""
    monkeypatch.setattr(settings, "bridge_url", "")
    monkeypatch.setattr(settings, "bridge_token", "")
    monkeypatch.setattr(settings, "github_token", "")
    yield env


async def create_profile(client, name="Tester") -> dict:
    resp = await client.post("/api/v1/profiles", json={"display_name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def wait_until(predicate, timeout=5.0, interval=0.05):
    """Poll an async predicate until truthy or timeout."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        result = await predicate()
        if result:
            return result
        await asyncio.sleep(interval)
    raise AssertionError("condition not met within timeout")
