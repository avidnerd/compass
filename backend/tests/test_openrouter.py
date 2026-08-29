"""Free-only gateway invariants."""
import pytest

from app import openrouter
from app.llm import ReactionBatch
from conftest import FREE_CATALOG


def entry(model_id):
    return next(m for m in FREE_CATALOG["data"] if m["id"] == model_id)


def test_catalog_filtering():
    assert openrouter.is_verified_free(entry("google/gemma-4-26b-a4b-it:free"))
    assert not openrouter.is_verified_free(entry("openrouter/auto"))
    assert not openrouter.is_verified_free(entry("openai/gpt-4o"))
    # aliases without :free are rejected even at zero price
    assert not openrouter.is_verified_free(
        {"id": "vendor/model", "pricing": {"prompt": "0", "completion": "0"},
         "supported_parameters": ["structured_outputs"]})
    # unknown pricing disqualifies
    assert not openrouter.is_verified_free(
        {"id": "vendor/model:free", "pricing": {}, "supported_parameters": ["structured_outputs"]})
    assert not openrouter.is_verified_free(
        {"id": "vendor/model:free", "pricing": {"prompt": None, "completion": "0"},
         "supported_parameters": ["structured_outputs"]})
    # missing structured output support disqualifies
    assert not openrouter.is_verified_free(
        {"id": "vendor/model:free", "pricing": {"prompt": "0", "completion": "0"},
         "supported_parameters": ["temperature"]})
    assert openrouter.supports_vision(
        entry("nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"))
    assert not openrouter.supports_vision(entry("google/gemma-4-26b-a4b-it:free"))


def test_preference_evaluation_no_pricing_leak():
    verdicts = openrouter.evaluate_preferences(FREE_CATALOG, [
        "google/gemma-4-26b-a4b-it:free", "openai/gpt-4o", "made/up:free"])
    assert verdicts[0]["status"] == "verified_free"
    assert verdicts[1]["status"] == "rejected_not_free"
    assert verdicts[2]["status"] == "not_in_catalog"
    for v in verdicts:
        assert set(v.keys()) == {"id", "status"}  # no pricing metadata exposed


async def test_resolve_prefers_configured_order(env):
    model = await openrouter.resolve_free_model()
    assert model is not None and model.id == "google/gemma-4-26b-a4b-it:free"


async def test_call_falls_back_to_second_free_model_only(env):
    env.llm.fail_models.add("google/gemma-4-26b-a4b-it:free")
    result, model_id = await openrouter.call_free_structured(
        "p1", "test", ReactionBatch, "sys", "user", use_cache=False)
    assert model_id == "openai/gpt-oss-20b:free"
    # never more than two distinct models per job, all :free (FakeLLM asserts)
    assert set(env.llm.requests) <= {"google/gemma-4-26b-a4b-it:free", "openai/gpt-oss-20b:free"}


async def test_no_paid_fallback_when_no_free_model(env, monkeypatch):
    async def paid_only_catalog(force=False):
        return {"data": [m for m in FREE_CATALOG["data"] if not m["id"].endswith(":free")]}
    monkeypatch.setattr(openrouter, "refresh_free_model_catalog", paid_only_catalog)
    with pytest.raises(openrouter.FreeModelUnavailable):
        await openrouter.call_free_structured("p1", "test", ReactionBatch, "sys", "user",
                                              use_cache=False)
    assert env.llm.requests == []  # nothing was ever sent


async def test_request_once_refuses_non_free_route():
    # The wire-level guard raises before any network I/O happens.
    with pytest.raises(openrouter.FreeModelUnavailable):
        await openrouter._request_once("openai/gpt-4o", [], ReactionBatch, 0.2)
    with pytest.raises(openrouter.FreeModelUnavailable):
        await openrouter._request_once("openrouter/auto", [], ReactionBatch, 0.2)


async def test_scan_model_preference_used_for_interest_scan(env):
    """The configured scan model is used for the scan even without the
    structured-outputs flag — but never enters the default chain."""
    from app.config import settings
    from app.llm import infer_interest_profile
    assert settings.openrouter_scan_model == "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"

    _draft, model_id = await infer_interest_profile(
        "p1", [{"name": "Notes", "kind": "doc", "excerpt": "gardening"}], "fp1")
    assert model_id == "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"

    # default chain (e.g. reactions) still skips models without structured support
    env.llm.requests.clear()
    await openrouter.call_free_structured("p1", "test", ReactionBatch, "sys", "u2", use_cache=False)
    assert env.llm.requests == ["google/gemma-4-26b-a4b-it:free"]


async def test_scan_model_falls_back_when_it_fails(env):
    env.llm.fail_models.add("nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free")
    from app.llm import infer_interest_profile
    _draft, model_id = await infer_interest_profile(
        "p2", [{"name": "Notes", "kind": "doc", "excerpt": "gardening"}], "fp2")
    assert model_id == "google/gemma-4-26b-a4b-it:free"


def test_lenient_parse_extracts_json_from_prose():
    from app.openrouter import _parse_structured
    wrapped = "Thinking about it...\n```json\n" + \
        '{"reaction": "Yay!", "encouragement": "Go!", "journal_memory": "A good day."}' + "\n```"
    result = _parse_structured(wrapped, ReactionBatch)
    assert result.reaction == "Yay!"


async def test_llm_cache_avoids_second_call(env):
    r1, m1 = await openrouter.call_free_structured("p1", "test", ReactionBatch, "sys", "same-user")
    n = len(env.llm.requests)
    r2, m2 = await openrouter.call_free_structured("p1", "test", ReactionBatch, "sys", "same-user")
    assert len(env.llm.requests) == n  # served from llm_cache
    assert r1 == r2 and m1 == m2


# --------------------------------------------- error bodies served with a 200

@pytest.mark.parametrize("body, expected", [
    ({"error": {"code": 429, "message": "rate limit exceeded"}}, openrouter._Transient),
    ({"error": {"message": "upstream provider is down"}}, openrouter.FreeModelUnavailable),
    ({"choices": []}, openrouter.FreeModelUnavailable),
    ({}, openrouter.FreeModelUnavailable),
])
async def test_a_200_carrying_an_error_body_is_not_a_crash(monkeypatch, body, expected):
    """OpenRouter reports free-tier limits and provider outages in-band, with a
    200. Reading ["choices"] blindly raised a bare KeyError that killed the
    worker and stranded whatever queued the job — a quest stuck in 'planning'
    forever, with nothing shown to the user."""
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    monkeypatch.setattr(openrouter, "_client",
                        httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                          base_url="https://openrouter.ai/api/v1"))
    monkeypatch.setattr(openrouter, "_auth_state", "ok")
    with pytest.raises(expected):
        await openrouter._request_once(
            "google/gemma-4-26b-a4b-it:free", [{"role": "user", "content": "hi"}],
            ReactionBatch, 0.2)
    await openrouter._client.aclose()
