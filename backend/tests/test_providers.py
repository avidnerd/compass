"""The data plane: the Apps Script bridge + a GitHub PAT.

These tests drive the real `bridge`/`github` HTTP clients through mock
transports, so URL validation, token handling, error mapping, and the
capability registry are all exercised — only the network is faked.
"""
import json
import re

import pytest

from app import bridge, capabilities, github, providers
from conftest import BRIDGE_TOKEN, BRIDGE_URL, GITHUB_TOKEN, create_profile, wait_until
from test_college import DASHBOARD_ID, TABS


async def adopt_bridge(client, url: str = BRIDGE_URL, token: str = BRIDGE_TOKEN):
    return await client.put("/api/v1/providers/bridge", json={"url": url, "token": token})


# ------------------------------------------------------------- adoption

async def test_bridge_handshake_adopts_the_provider(unconfigured):
    env = unconfigured
    await create_profile(env.client)
    assert (await env.client.get("/api/v1/providers")).json()["data"]["active"] is None

    resp = await adopt_bridge(env.client)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["active"] == "bridge"
    assert data["bridge"]["configured"] is True
    assert data["handshake"]["ok"] is True
    assert ("bridge.hello", {}) in env.script.calls


async def test_credentials_are_never_returned_to_the_client(unconfigured):
    env = unconfigured
    await create_profile(env.client)
    await adopt_bridge(env.client)
    await env.client.put("/api/v1/providers/github", json={"token": GITHUB_TOKEN})

    body = (await env.client.get("/api/v1/providers")).text
    assert BRIDGE_TOKEN not in body
    assert GITHUB_TOKEN not in body
    assert BRIDGE_URL not in body
    # Only a masked hint, enough to tell two tokens apart.
    assert json.loads(body)["data"]["bridge"]["token_hint"] == f"…{BRIDGE_TOKEN[-4:]}"


async def test_bad_token_is_rejected_and_not_stored(unconfigured):
    env = unconfigured
    await create_profile(env.client)
    resp = await adopt_bridge(env.client, token="wrong-token-entirely")
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "bridge_unauthorized"

    state = (await env.client.get("/api/v1/providers")).json()["data"]
    assert state["bridge"]["configured"] is False
    assert state["active"] is None


async def test_a_non_apps_script_url_is_refused(unconfigured):
    env = unconfigured
    await create_profile(env.client)
    resp = await adopt_bridge(env.client, url="https://evil.example.com/exec")
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "bridge_url_invalid"


async def test_a_sign_in_page_produces_an_actionable_error(unconfigured):
    """The classic misconfiguration: deployed without 'Anyone' access."""
    env = unconfigured
    await create_profile(env.client)
    env.script.serve_sign_in_page = True
    resp = await adopt_bridge(env.client)
    assert resp.json()["error"]["code"] == "bridge_not_public"
    assert "Anyone" in resp.json()["error"]["message"]


async def test_no_provider_at_all_is_a_clear_error(unconfigured):
    env = unconfigured
    await create_profile(env.client)

    state = (await env.client.get("/api/v1/providers")).json()["data"]
    assert state["active"] is None
    resp = await env.client.post("/api/v1/college/detect")
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "provider_not_configured"

    states = {s["connector"]: s for s in (await env.client.get("/api/v1/connections")).json()["data"]}
    assert states["google_drive"]["error_code"] == "provider_not_configured"


# ------------------------------------------------------- capability surface

async def test_the_capability_surface_is_read_only():
    """No provider exposes a write: the bridge serves a fixed read-only list and
    the GitHub client only ever issues GETs."""
    writes = re.compile(r"(create|send|update|delete|upload|move|copy|insert|append|write|"
                        r"modify|remove|add_|set_|patch|share|permission|trash|archive|reply|"
                        r"draft|compose)", re.IGNORECASE)
    registry = capabilities.build_bridge_registry(providers.bridge_capabilities())
    assert registry.available
    for capability in registry.available:
        assert not writes.search(capability), capability
    assert set(github.CAPABILITIES) <= registry.available


async def test_registry_is_honest_about_google_meet(env):
    await create_profile(env.client)

    registry = capabilities.current_registry()
    assert registry.resolve("drive.list_files") == "drive.list_files"
    assert registry.resolve("calendar.list_calendars") is not None
    # Meet needs a Cloud project, which is the cost this path avoids. Say so.
    assert registry.resolve("meet.list_conference_records") is None
    assert registry.connector_status("google_meet") == "unsupported"
    assert registry.connector_status("google_drive") == "supported"
    assert registry.connector_status("gmail") == "supported"

    states = {s["connector"]: s for s in (await env.client.get("/api/v1/connections")).json()["data"]}
    assert states["google_drive"]["status"] == "connected"
    assert states["google_meet"]["status"] == "unsupported"
    # meet_attended must not be offered as evidence Compass cannot observe.
    quests = (await env.client.get("/api/v1/quests")).json()["data"]
    assert "meet_attended" not in quests["available_evidence_types"]
    assert "file_created" in quests["available_evidence_types"]


# ------------------------------------------------------------ the payoff

async def test_college_os_works_end_to_end_on_the_bridge(env):
    await create_profile(env.client)
    env.script.files = [
        {"id": DASHBOARD_ID, "name": "COLLEGE DASHBOARD",
         "mime_type": "application/vnd.google-apps.spreadsheet",
         "modified_time": "2026-08-20T10:00:00Z"},
        {"id": "folder-college", "name": "COLLEGE",
         "mime_type": "application/vnd.google-apps.folder", "modified_time": "2026-08-01T10:00:00Z"},
    ]
    env.script.sheets = {DASHBOARD_ID: TABS}
    env.script.calendars = [{"id": "cal-1", "summary": "🎓 Academic"}]

    link = (await env.client.post("/api/v1/college/detect")).json()["data"]
    assert link["status"] == "linked"
    assert link["dashboard_file_id"] == DASHBOARD_ID

    body = (await env.client.get("/api/v1/college")).json()["data"]
    assert body["dashboard"]["missing_tabs"] == []
    lab = next(d for d in body["importable"] if d["title"] == "Join a research lab")

    created = (await env.client.post("/api/v1/college/quests:import",
                                     json={"source_keys": [lab["source_key"]]})).json()["data"]
    quest_id = created["created"][0]["quest_id"]
    await wait_until(lambda: _planned(env.client, quest_id))

    # Every read went through the Apps Script bridge.
    assert {fn for fn, _ in env.script.calls} >= {"drive.list_files", "sheets.get_values"}


async def _planned(client, quest_id):
    quest = (await client.get(f"/api/v1/quests/{quest_id}")).json()["data"]
    return len(quest["subgoals"]) > 0


async def test_a_github_pat_is_all_the_code_telemetry_needs(env):
    from datetime import timedelta

    from app import telemetry
    from app.services import profiles as profile_service
    from app.util import now

    profile_row = await create_profile(env.client)
    env.github.repos = [{"full_name": "avidnerd/sensor-rig", "private": False}]
    env.github.commits = {"avidnerd/sensor-rig": [
        {"sha": "abc123", "commit": {"message": "Add sensor loop",
                                     "author": {"date": "2026-08-20T10:00:00Z"}}}]}
    env.github.pulls = {"avidnerd/sensor-rig": [
        {"number": 7, "title": "Sensor loop", "state": "closed",
         "created_at": "2026-08-19T10:00:00Z", "merged_at": "2026-08-20T11:00:00Z"}]}

    profile = await profile_service.get_profile(profile_row["profile"]["id"])
    activity, _meta = await telemetry.github_activity(profile, now() - timedelta(days=7))
    assert activity["repos"] == ["avidnerd/sensor-rig"]
    assert activity["commits"][0]["sha"] == "abc123"
    # The list endpoint has no `merged` field; merged_at is the same fact.
    assert activity["pull_requests"][0]["merged"] is True


async def test_github_stays_disconnected_until_a_token_is_added(unconfigured):
    env = unconfigured
    await create_profile(env.client)
    await adopt_bridge(env.client)

    states = {s["connector"]: s for s in (await env.client.get("/api/v1/connections")).json()["data"]}
    assert states["github"]["status"] == "disconnected"
    assert states["github"]["error_code"] == "github_not_configured"


async def test_a_rejected_github_token_is_not_saved(unconfigured):
    env = unconfigured
    await create_profile(env.client)
    await adopt_bridge(env.client)
    env.github.unauthorized = True

    resp = await env.client.put("/api/v1/providers/github", json={"token": "ghp_wrongtoken12345"})
    assert resp.status_code == 502
    state = (await env.client.get("/api/v1/providers")).json()["data"]
    assert state["github"]["configured"] is False


async def test_interest_scan_runs_on_the_bridge(env):
    """The scan reads Drive + Docs — a good proof that content reads work too."""
    await create_profile(env.client)
    env.script.files = [
        {"id": "doc-1", "name": "Sensor rig notes",
         "mime_type": "application/vnd.google-apps.document",
         "modified_time": "2026-08-20T10:00:00Z"},
    ]
    env.script.doc_texts["doc-1"] = "soldering the moisture sensor rig " * 40
    await env.client.patch("/api/v1/me", json={"scan_consented": True})
    resp = await env.client.post("/api/v1/interest-scans")
    assert resp.status_code == 202

    async def scanned():
        got = await env.client.get("/api/v1/interest-profile")
        return got.status_code == 200
    await wait_until(scanned)
    assert "docs.get_text" in {fn for fn, _ in env.script.calls}


@pytest.mark.parametrize("capability", ["drive.list_files", "gmail.list_messages"])
async def test_bridge_calls_carry_the_token_and_capability(env, capability):
    await create_profile(env.client)
    payload = await bridge.call(BRIDGE_URL, BRIDGE_TOKEN, capability, {"page_size": 1})
    assert "error" not in payload
    assert capability in {fn for fn, _ in env.script.calls}


# ------------------------------------------------- credentials at rest

async def test_saved_credentials_are_encrypted_in_the_database(unconfigured):
    """A read of the SQLite file must not hand over the user's accounts."""
    from app import db

    env = unconfigured
    await create_profile(env.client)
    await adopt_bridge(env.client)
    await env.client.put("/api/v1/providers/github", json={"token": GITHUB_TOKEN})

    cur = await db.get().execute("SELECT provider, config_json FROM provider_credentials")
    stored = {r["provider"]: r["config_json"] for r in await cur.fetchall()}
    for provider in ("bridge", "github"):
        assert BRIDGE_TOKEN not in stored[provider]
        assert GITHUB_TOKEN not in stored[provider]
        assert BRIDGE_URL not in stored[provider]
        assert stored[provider].startswith("v1:")

    # ...and Compass can still read them back.
    resolved = await providers.credentials(
        (await env.client.get("/api/v1/me")).json()["data"]["id"])
    assert resolved["bridge"]["token"] == BRIDGE_TOKEN
    assert resolved["github"]["token"] == GITHUB_TOKEN


async def test_rows_written_before_encryption_still_load(unconfigured):
    """An existing install upgrades without a migration."""
    from app import crypto, db

    env = unconfigured
    profile_id = (await create_profile(env.client))["profile"]["id"]
    await db.get().execute(
        "INSERT INTO provider_credentials (profile_id, provider, config_json, status, updated_at)"
        " VALUES (?, 'bridge', ?, 'ok', '2026-01-01T00:00:00Z')",
        (profile_id, json.dumps({"url": BRIDGE_URL, "token": BRIDGE_TOKEN})))
    await db.get().commit()

    resolved = await providers.credentials(profile_id)
    assert resolved["bridge"]["token"] == BRIDGE_TOKEN

    # Re-saving seals it.
    await providers.save_credentials(profile_id, "bridge", resolved["bridge"])
    cur = await db.get().execute(
        "SELECT config_json FROM provider_credentials WHERE profile_id = ? AND provider = 'bridge'",
        (profile_id,))
    assert (await cur.fetchone())["config_json"].startswith("v1:")
    assert crypto.available()


async def test_a_changed_app_secret_fails_loudly(unconfigured, monkeypatch):
    """Better a clear error than silently acting as though nothing is connected."""
    from app import crypto
    from app.config import settings as app_settings

    env = unconfigured
    profile_id = (await create_profile(env.client))["profile"]["id"]
    await adopt_bridge(env.client)

    monkeypatch.setattr(app_settings, "app_secret", "a-completely-different-secret")
    crypto.reset_cache()
    with pytest.raises(RuntimeError, match="COMPASS_APP_SECRET has changed"):
        await providers.credentials(profile_id)
