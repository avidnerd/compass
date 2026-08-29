"""Free-only OpenRouter gateway.

Every LLM call in Compass passes through call_free_structured(). The
invariants enforced here, and only here:

- Only models that end in `:free`, report zero prompt AND completion pricing,
  and support structured outputs may be called.
- `openrouter/auto`, paid variants, aliases without `:free`, and models with
  unknown pricing are rejected.
- If nothing qualifies, FreeModelUnavailable is raised — callers fall back to
  transparent manual behavior. There is no paid fallback, ever.
"""
import asyncio
import json
import logging
import random
from dataclasses import dataclass
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from . import cache
from .config import settings

logger = logging.getLogger("compass.openrouter")

T = TypeVar("T", bound=BaseModel)

# Free endpoints have strict rate limits: one in-flight request globally.
_llm_semaphore = asyncio.Semaphore(1)
# One active OpenRouter job per profile.
_profile_locks: dict[str, asyncio.Lock] = {}

_client: httpx.AsyncClient | None = None


class FreeModelUnavailable(Exception):
    """No verified-free model is currently usable."""


# Tracks whether completions auth works (the catalog endpoint needs no auth,
# so catalog success alone must never imply "available").
_auth_state: str = "unknown"  # unknown | ok | failed


def auth_state() -> str:
    return _auth_state


class LLMOutputInvalid(Exception):
    """The model returned output that failed schema validation twice."""


@dataclass
class FreeModel:
    id: str
    name: str
    structured: bool = True  # advertises response_format/structured_outputs


def profile_lock(profile_id: str) -> asyncio.Lock:
    if profile_id not in _profile_locks:
        _profile_locks[profile_id] = asyncio.Lock()
    return _profile_locks[profile_id]


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=settings.openrouter_api_base,
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
                "X-Title": "Compass (local)",
            },
            timeout=30.0,
        )
    return _client


async def aclose() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def refresh_free_model_catalog(force: bool = False) -> dict:
    """Fetch (or reuse) the OpenRouter model catalog; cached 24h globally."""
    async def fetch() -> dict:
        resp = await client().get("/models")
        resp.raise_for_status()
        return resp.json()

    payload, _meta = await cache.get_or_fetch(
        scope_id="global",
        connector="openrouter",
        capability="models.list",
        arguments={},
        ttl_seconds=settings.ttl_model_catalog,
        fetch_fn=fetch,
        force=force,
        serve_stale_on_error=True,
    )
    return payload


def _price_is_zero(value) -> bool:
    if value is None:
        return False
    try:
        return float(value) == 0.0
    except (TypeError, ValueError):
        return False


def supports_structured(entry: dict) -> bool:
    supported = entry.get("supported_parameters") or []
    return "structured_outputs" in supported or "response_format" in supported


def supports_vision(entry: dict) -> bool:
    """Return true only when the catalog explicitly advertises image input."""
    architecture = entry.get("architecture") or {}
    modalities = architecture.get("input_modalities") or entry.get("input_modalities") or []
    if isinstance(modalities, str):
        modalities = [modalities]
    if any(str(modality).lower() == "image" for modality in modalities):
        return True
    modality = str(architecture.get("modality") or entry.get("modality") or "").lower()
    return "image" in modality


def is_verified_free(entry: dict, require_structured: bool = True) -> bool:
    """A model qualifies only if every check passes; unknowns disqualify.

    require_structured=False is used only for an explicit user-configured
    per-purpose preference; the free/zero-price/no-auto checks never relax.
    """
    model_id = entry.get("id") or ""
    if not model_id.endswith(":free"):
        return False
    if model_id == "openrouter/auto" or model_id.startswith("openrouter/"):
        return False
    pricing = entry.get("pricing") or {}
    if not (_price_is_zero(pricing.get("prompt")) and _price_is_zero(pricing.get("completion"))):
        return False
    if require_structured and not supports_structured(entry):
        return False
    return True


def evaluate_preferences(catalog: dict, preferences: list[str]) -> list[dict]:
    """Per-preference verdicts for /system/free-models (no pricing echoed)."""
    by_id = {m.get("id"): m for m in catalog.get("data") or []}
    out = []
    for model_id in preferences:
        entry = by_id.get(model_id)
        if entry is None:
            out.append({"id": model_id, "status": "not_in_catalog"})
        elif is_verified_free(entry):
            out.append({"id": model_id, "status": "verified_free"})
        else:
            out.append({"id": model_id, "status": "rejected_not_free"})
    return out


def preference_order() -> list[str]:
    return [settings.openrouter_model, *settings.openrouter_fallback_models]


async def resolve_free_model(preferences: list[str] | None = None, force: bool = False) -> FreeModel | None:
    if not settings.openrouter_api_key:
        return None
    try:
        catalog = await refresh_free_model_catalog(force=force)
    except Exception:
        logger.warning("[openrouter] catalog fetch failed; treating free models as unavailable")
        return None
    by_id = {m.get("id"): m for m in catalog.get("data") or []}
    for model_id in preferences or preference_order():
        entry = by_id.get(model_id)
        if entry is not None and is_verified_free(entry):
            return FreeModel(id=model_id, name=entry.get("name") or model_id)
    return None


async def resolve_candidates(limit: int = 2, preferences: list[str] | None = None,
                             allow_missing_structured: bool = False,
                             require_vision: bool = False) -> list[FreeModel]:
    """Up to `limit` distinct verified-free models, in preference order.

    `preferences` is prepended to the default order (deduplicated).
    allow_missing_structured tolerates a missing structured-outputs flag for
    the explicitly preferred ids only — never for the default chain.
    """
    if not settings.openrouter_api_key:
        return []
    try:
        catalog = await refresh_free_model_catalog()
    except Exception:
        return []
    by_id = {m.get("id"): m for m in catalog.get("data") or []}
    preferred = list(preferences or [])
    order = preferred + [m for m in preference_order() if m not in preferred]
    found: list[FreeModel] = []
    for model_id in order:
        entry = by_id.get(model_id)
        if entry is None:
            continue
        if require_vision and not supports_vision(entry):
            continue
        relaxed = allow_missing_structured and model_id in preferred
        if is_verified_free(entry, require_structured=not relaxed):
            found.append(FreeModel(id=model_id, name=entry.get("name") or model_id,
                                   structured=supports_structured(entry)))
        if len(found) >= limit:
            break
    return found


def _schema_for(schema_model: type[BaseModel]) -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema_model.__name__,
            "strict": True,
            "schema": schema_model.model_json_schema(),
        },
    }


async def _request_once(model_id: str, messages: list[dict], schema_model: type[BaseModel],
                        temperature: float) -> str:
    # Hard invariant: never let a non-:free model id or the auto-router
    # reach the wire, no matter what upstream code passed in.
    if not model_id.endswith(":free") or model_id == "openrouter/auto":
        raise FreeModelUnavailable(f"Refusing non-free model route: {model_id}")
    body = {
        "model": model_id,
        "messages": messages,
        "temperature": temperature,
        "response_format": _schema_for(schema_model),
    }
    resp = await client().post("/chat/completions", json=body)
    global _auth_state
    if resp.status_code in (401, 403):
        _auth_state = "failed"
        logger.warning("[openrouter] completions auth rejected (%s) — check OPENROUTER_API_KEY",
                       resp.status_code)
    if resp.status_code == 429 or resp.status_code >= 500:
        retry_after = resp.headers.get("Retry-After")
        raise _Transient(retry_after)
    resp.raise_for_status()
    _auth_state = "ok"
    data = resp.json()
    # A 200 can still carry an error body: free models report rate limits and
    # provider outages in-band. Reading ["choices"] blindly turned that into a
    # raw KeyError that killed the job and stranded whatever queued it.
    if "choices" not in data or not data["choices"]:
        err = data.get("error") or {}
        code = err.get("code")
        message = str(err.get("message") or "no completion returned")[:200]
        logger.warning("[openrouter] %s returned no choices: %s", model_id, message)
        if code in (429, "429", "rate_limit_exceeded") or "rate" in message.lower():
            raise _Transient(None)
        raise FreeModelUnavailable(f"{model_id} returned no completion: {message}")
    return data["choices"][0]["message"]["content"]


class _Transient(Exception):
    def __init__(self, retry_after: str | None):
        super().__init__("transient upstream error")
        self.retry_after = retry_after


def _parse_structured(content: str, schema_model: type[T]) -> T:
    """Validate model output, tolerating markdown fences and reasoning prose
    around a single JSON object (needed for models without native
    structured-output support)."""
    try:
        return schema_model.model_validate_json(content)
    except ValidationError:
        start, end = content.find("{"), content.rfind("}")
        if start != -1 and end > start:
            return schema_model.model_validate_json(content[start:end + 1])
        raise


async def _attempt_model(model: FreeModel, messages: list[dict], schema_model: type[T],
                         temperature: float) -> T:
    model_id = model.id
    if not model.structured:
        # No native response_format support: instruct + parse leniently.
        schema = schema_model.model_json_schema()
        messages = messages + [{
            "role": "system",
            "content": "Respond with ONLY one valid JSON object matching this JSON Schema — "
                       f"no prose, no markdown fences:\n{schema}",
        }]
    delay = 1.0
    for attempt in range(3):  # first try + at most 2 transient retries
        try:
            content = await _request_once(model_id, messages, schema_model, temperature)
        except _Transient as exc:
            if attempt == 2:
                raise
            wait = delay
            if exc.retry_after:
                try:
                    wait = max(wait, float(exc.retry_after))
                except ValueError:
                    pass
            await asyncio.sleep(min(wait + random.uniform(0, 0.5), 15))
            delay *= 2
            continue
        try:
            return _parse_structured(content, schema_model)
        except ValidationError as err:
            # One compact-repair retry for malformed structured output.
            compact = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in err.errors()[:5])
            repair = messages + [
                {"role": "assistant", "content": content},
                {"role": "user", "content": f"Your JSON failed validation: {compact}. "
                                            "Reply again with ONLY corrected JSON matching the schema."},
            ]
            content2 = await _request_once(model_id, repair, schema_model, temperature)
            try:
                return _parse_structured(content2, schema_model)
            except ValidationError as err2:
                raise LLMOutputInvalid(str(err2)) from err2
    raise LLMOutputInvalid("unreachable")


async def call_free_structured(
    profile_id: str,
    purpose: str,
    schema_model: type[T],
    system: str,
    user: str,
    temperature: float = 0.2,
    cache_key_material: dict | None = None,
    cache_ttl_seconds: int | None = None,  # None = immutable
    use_cache: bool = True,
    preferred_models: list[str] | None = None,
    allow_missing_structured: bool = False,
) -> tuple[T, str]:
    """Run one structured LLM job on a verified-free model.

    Returns (validated_result, model_id). Raises FreeModelUnavailable or
    LLMOutputInvalid; callers must then use their deterministic fallback.
    """
    key_material = {
        "system": system, "user": user, "temperature": temperature,
        "schema": schema_model.__name__, **(cache_key_material or {}),
    }
    if use_cache:
        cached = await cache.llm_get(profile_id, purpose, key_material)
        if cached is not None:
            return schema_model.model_validate(cached["result"]), cached["model_id"]

    candidates = await resolve_candidates(limit=2, preferences=preferred_models,
                                          allow_missing_structured=allow_missing_structured)
    if not candidates:
        raise FreeModelUnavailable("No verified-free OpenRouter model available.")

    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    last_error: Exception | None = None
    async with profile_lock(profile_id):
        async with _llm_semaphore:
            for model in candidates:  # at most two different free models per job
                try:
                    result = await _attempt_model(model, messages, schema_model, temperature)
                except (FreeModelUnavailable, LLMOutputInvalid, _Transient, httpx.HTTPError) as exc:
                    logger.warning("[openrouter] model %s failed for %s: %s", model.id, purpose,
                                   type(exc).__name__)
                    last_error = exc
                    continue
                if use_cache:
                    await cache.llm_put(profile_id, purpose, key_material, model.id,
                                        {"result": result.model_dump(), "model_id": model.id},
                                        ttl_seconds=cache_ttl_seconds)
                return result, model.id
    if isinstance(last_error, LLMOutputInvalid):
        raise last_error
    raise FreeModelUnavailable("All verified-free models failed.") from last_error


async def call_free_vision_structured(
    profile_id: str,
    purpose: str,
    schema_model: type[T],
    system: str,
    user: str,
    images: list[tuple[str, str]],
    temperature: float = 0.1,
    preferred_models: list[str] | None = None,
) -> tuple[T, str]:
    """Run a structured multimodal job on a catalog-verified free model.

    ``images`` contains (MIME type, base64 payload) pairs. Calls are never
    cached because the screenshots are deliberately ephemeral and must not
    leak into Compass's persistent LLM cache.
    """
    if not images:
        raise ValueError("At least one image is required for a vision call.")
    candidates = await resolve_candidates(
        limit=2,
        preferences=preferred_models,
        allow_missing_structured=True,
        require_vision=True,
    )
    if not candidates:
        raise FreeModelUnavailable("No verified-free image-capable model is available.")

    content: list[dict] = [{"type": "text", "text": user}]
    for mime_type, payload in images:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime_type};base64,{payload}"},
        })
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": content}]

    last_error: Exception | None = None
    async with profile_lock(profile_id):
        async with _llm_semaphore:
            for model in candidates:
                try:
                    result = await _attempt_model(model, messages, schema_model, temperature)
                except (FreeModelUnavailable, LLMOutputInvalid, _Transient, httpx.HTTPError) as exc:
                    logger.warning("[openrouter] vision model %s failed for %s: %s",
                                   model.id, purpose, type(exc).__name__)
                    last_error = exc
                    continue
                return result, model.id
    if isinstance(last_error, LLMOutputInvalid):
        raise last_error
    raise FreeModelUnavailable("All verified-free image-capable models failed.") from last_error
