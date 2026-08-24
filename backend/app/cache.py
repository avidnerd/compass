"""User-scoped SQLite caches: provider tool responses, analytics rollups, and
LLM outputs. Every key includes scope (profile), connector, logical
capability, canonical arguments, and schema version.
"""
import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta

from . import db
from .util import canonical_json, now, now_iso, parse_iso, sha256_hex

logger = logging.getLogger("compass.cache")

SCHEMA_VERSION = 1

_locks: dict[str, asyncio.Lock] = {}


def _lock(key: str) -> asyncio.Lock:
    if key not in _locks:
        _locks[key] = asyncio.Lock()
    return _locks[key]


def canonical_cache_key(scope_id: str, connector: str, capability: str, arguments: dict,
                        schema_version: int = SCHEMA_VERSION) -> str:
    return sha256_hex(f"{scope_id}::{connector}::{capability}::{canonical_json(arguments)}::v{schema_version}")


async def _bump(scope_id: str, counter: str, n: int = 1) -> None:
    conn = db.get()
    await conn.execute(
        """INSERT INTO cache_counters (scope_id, counter, value) VALUES (?, ?, ?)
           ON CONFLICT(scope_id, counter) DO UPDATE SET value = value + excluded.value""",
        (scope_id, counter, n),
    )
    await conn.commit()


async def get_or_fetch(
    scope_id: str,
    connector: str,
    capability: str,
    arguments: dict,
    ttl_seconds: int,
    fetch_fn: Callable[[], Awaitable[dict]],
    force: bool = False,
    serve_stale_on_error: bool = False,
) -> tuple[dict, dict]:
    """Return (payload, meta) for a provider call, hitting the network only on
    miss/expiry/force. Single-flight per key. meta includes from_cache,
    stale, fetched_at, expires_at."""
    key = canonical_cache_key(scope_id, connector, capability, arguments)
    conn = db.get()

    async with _lock(key):
        row = None
        if not force:
            cur = await conn.execute("SELECT * FROM tool_cache WHERE cache_key = ?", (key,))
            row = await cur.fetchone()
            if row and parse_iso(row["expires_at"]) > now():
                await conn.execute(
                    "UPDATE tool_cache SET hit_count = hit_count + 1, last_hit_at = ? WHERE cache_key = ?",
                    (now_iso(), key),
                )
                await conn.commit()
                await _bump(scope_id, "hits")
                await _bump(scope_id, "avoided_calls")
                return json.loads(row["response_json"]), {
                    "from_cache": True, "stale": False,
                    "fetched_at": row["fetched_at"], "expires_at": row["expires_at"],
                }

        await _bump(scope_id, "misses")
        try:
            payload = await fetch_fn()
        except Exception:
            if serve_stale_on_error and row is not None:
                await conn.execute(
                    "UPDATE tool_cache SET stale_hits = stale_hits + 1, last_hit_at = ? WHERE cache_key = ?",
                    (now_iso(), key),
                )
                await conn.commit()
                await _bump(scope_id, "stale_serves")
                logger.warning("[cache] serving STALE %s/%s for scope=%s", connector, capability, scope_id[:8])
                return json.loads(row["response_json"]), {
                    "from_cache": True, "stale": True,
                    "fetched_at": row["fetched_at"], "expires_at": row["expires_at"],
                }
            raise

        fetched_at = now_iso()
        expires_at = (now() + timedelta(seconds=ttl_seconds)).isoformat()
        await conn.execute(
            """INSERT INTO tool_cache (cache_key, scope_id, connector, capability, args_json, response_json,
                                       fetched_at, expires_at, hit_count, stale_hits, last_hit_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, NULL)
               ON CONFLICT(cache_key) DO UPDATE SET
                 response_json = excluded.response_json, fetched_at = excluded.fetched_at,
                 expires_at = excluded.expires_at, hit_count = 0, stale_hits = 0, last_hit_at = NULL""",
            (key, scope_id, connector, capability, canonical_json(arguments), json.dumps(payload),
             fetched_at, expires_at),
        )
        await conn.commit()
        return payload, {"from_cache": False, "stale": False, "fetched_at": fetched_at, "expires_at": expires_at}


async def get_or_compute(
    profile_id: str,
    metric_name: str,
    params: dict,
    ttl_seconds: int,
    compute_fn: Callable[[], Awaitable[dict]] | Callable[[], dict],
    force: bool = False,
) -> tuple[dict, dict]:
    key = canonical_cache_key(profile_id, "analytics", metric_name, params)
    conn = db.get()
    async with _lock(key):
        if not force:
            cur = await conn.execute("SELECT * FROM analytics_cache WHERE cache_key = ?", (key,))
            row = await cur.fetchone()
            if row and parse_iso(row["expires_at"]) > now():
                await conn.execute(
                    "UPDATE analytics_cache SET hit_count = hit_count + 1, last_hit_at = ? WHERE cache_key = ?",
                    (now_iso(), key),
                )
                await conn.commit()
                await _bump(profile_id, "hits")
                return json.loads(row["result_json"]), {
                    "from_cache": True, "stale": False,
                    "computed_at": row["computed_at"], "expires_at": row["expires_at"],
                }
        await _bump(profile_id, "misses")
        result = compute_fn()
        if asyncio.iscoroutine(result):
            result = await result
        computed_at = now_iso()
        expires_at = (now() + timedelta(seconds=ttl_seconds)).isoformat()
        await conn.execute(
            """INSERT INTO analytics_cache (cache_key, profile_id, metric_name, params_json, result_json,
                                            computed_at, expires_at, hit_count, stale_hits, last_hit_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, NULL)
               ON CONFLICT(cache_key) DO UPDATE SET
                 result_json = excluded.result_json, computed_at = excluded.computed_at,
                 expires_at = excluded.expires_at, hit_count = 0, stale_hits = 0, last_hit_at = NULL""",
            (key, profile_id, metric_name, canonical_json(params), json.dumps(result), computed_at, expires_at),
        )
        await conn.commit()
        return result, {"from_cache": False, "stale": False, "computed_at": computed_at, "expires_at": expires_at}


async def llm_get(profile_id: str, purpose: str, key_material: dict) -> dict | None:
    key = canonical_cache_key(profile_id, "llm", purpose, key_material)
    cur = await db.get().execute("SELECT * FROM llm_cache WHERE cache_key = ?", (key,))
    row = await cur.fetchone()
    if row is None:
        return None
    if row["expires_at"] is not None and parse_iso(row["expires_at"]) <= now():
        return None
    await _bump(profile_id, "hits")
    await _bump(profile_id, "avoided_calls")
    return json.loads(row["result_json"])


async def llm_put(profile_id: str, purpose: str, key_material: dict, model_id: str,
                  result: dict, ttl_seconds: int | None = None) -> None:
    key = canonical_cache_key(profile_id, "llm", purpose, key_material)
    expires_at = (now() + timedelta(seconds=ttl_seconds)).isoformat() if ttl_seconds else None
    await db.get().execute(
        """INSERT INTO llm_cache (cache_key, profile_id, purpose, model_id, result_json, created_at, expires_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(cache_key) DO UPDATE SET
             result_json = excluded.result_json, model_id = excluded.model_id,
             created_at = excluded.created_at, expires_at = excluded.expires_at""",
        (key, profile_id, purpose, model_id, json.dumps(result), now_iso(), expires_at),
    )
    await db.get().commit()


async def connector_generation(profile_id: str, connector: str) -> int:
    cur = await db.get().execute(
        "SELECT generation FROM connector_states WHERE profile_id = ? AND connector = ?",
        (profile_id, connector),
    )
    row = await cur.fetchone()
    return row["generation"] if row else 0


async def invalidate_connector(profile_id: str, connector: str) -> int:
    """Delete this profile+connector's cached tool rows and bump its
    generation (analytics keys embed generations, so they roll naturally)."""
    conn = db.get()
    cur = await conn.execute(
        "DELETE FROM tool_cache WHERE scope_id = ? AND connector = ?", (profile_id, connector)
    )
    n = cur.rowcount
    await conn.execute(
        """INSERT INTO connector_states (profile_id, connector, generation) VALUES (?, ?, 1)
           ON CONFLICT(profile_id, connector) DO UPDATE SET generation = generation + 1""",
        (profile_id, connector),
    )
    await conn.commit()
    return n


async def cache_stats(profile_id: str) -> dict:
    conn = db.get()
    counters = {}
    cur = await conn.execute("SELECT counter, value FROM cache_counters WHERE scope_id = ?", (profile_id,))
    for row in await cur.fetchall():
        counters[row["counter"]] = row["value"]
    cur = await conn.execute(
        """SELECT connector, COUNT(*) AS rows, SUM(hit_count) AS hits, MAX(fetched_at) AS last_fetched_at,
                  SUM(CASE WHEN expires_at > ? THEN 1 ELSE 0 END) AS fresh_rows
           FROM tool_cache WHERE scope_id = ? GROUP BY connector""",
        (now_iso(), profile_id),
    )
    tools = [dict(r) for r in await cur.fetchall()]
    cur = await conn.execute(
        """SELECT metric_name, COUNT(*) AS rows, SUM(hit_count) AS hits, MAX(computed_at) AS last_computed_at
           FROM analytics_cache WHERE profile_id = ? GROUP BY metric_name""",
        (profile_id,),
    )
    metrics = [dict(r) for r in await cur.fetchall()]
    return {
        "hits": counters.get("hits", 0),
        "misses": counters.get("misses", 0),
        "stale_serves": counters.get("stale_serves", 0),
        "avoided_calls": counters.get("avoided_calls", 0),
        "tools": tools,
        "analytics": metrics,
    }


async def delete_profile_caches(profile_id: str) -> None:
    conn = db.get()
    for table, col in (("tool_cache", "scope_id"), ("analytics_cache", "profile_id"),
                       ("llm_cache", "profile_id"), ("cache_counters", "scope_id")):
        await conn.execute(f"DELETE FROM {table} WHERE {col} = ?", (profile_id,))
    await conn.commit()
