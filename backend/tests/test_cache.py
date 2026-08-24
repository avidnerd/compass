"""User-scoped cache isolation, canonicalization, generations."""
from app import cache


def test_canonical_key_stability_and_scoping():
    k1 = cache.canonical_cache_key("p1", "google_drive", "drive.list_files", {"a": 1, "b": 2})
    k2 = cache.canonical_cache_key("p1", "google_drive", "drive.list_files", {"b": 2, "a": 1})
    assert k1 == k2  # argument order canonicalized
    k3 = cache.canonical_cache_key("p2", "google_drive", "drive.list_files", {"a": 1, "b": 2})
    assert k1 != k3  # different profile, different key
    k4 = cache.canonical_cache_key("p1", "google_drive", "drive.list_files", {"a": 1, "b": 2},
                                   schema_version=2)
    assert k1 != k4  # schema version participates


async def test_cache_isolation_between_profiles(env):
    calls = {"n": 0}

    async def fetch():
        calls["n"] += 1
        return {"value": calls["n"]}

    p1, _ = await cache.get_or_fetch("profile-a", "google_drive", "drive.list_files", {}, 300, fetch)
    p2, _ = await cache.get_or_fetch("profile-b", "google_drive", "drive.list_files", {}, 300, fetch)
    assert p1["value"] == 1 and p2["value"] == 2  # no cross-profile reuse
    p1_again, meta = await cache.get_or_fetch("profile-a", "google_drive", "drive.list_files", {}, 300, fetch)
    assert p1_again["value"] == 1 and meta["from_cache"]


async def test_invalidate_connector_bumps_generation(env):
    from conftest import create_profile
    p1 = (await create_profile(env.client, "CacheOne"))["profile"]["id"]

    async def fetch():
        return {"v": 1}
    await cache.get_or_fetch(p1, "gmail", "gmail.sent_since", {"q": "x"}, 300, fetch)
    assert await cache.connector_generation(p1, "gmail") == 0
    n = await cache.invalidate_connector(p1, "gmail")
    assert n == 1
    assert await cache.connector_generation(p1, "gmail") == 1
    # a second profile's generation is untouched
    assert await cache.connector_generation("someone-else", "gmail") == 0


async def test_stale_serve_on_error(env):
    state = {"fail": False}

    async def fetch():
        if state["fail"]:
            raise RuntimeError("provider down")
        return {"v": "fresh"}

    await cache.get_or_fetch("p1", "github", "github.activity", {}, ttl_seconds=0, fetch_fn=fetch)
    state["fail"] = True
    payload, meta = await cache.get_or_fetch(
        "p1", "github", "github.activity", {}, ttl_seconds=0, fetch_fn=fetch,
        serve_stale_on_error=True)
    assert payload == {"v": "fresh"} and meta["stale"] is True
    stats = await cache.cache_stats("p1")
    assert stats["stale_serves"] >= 1


async def test_cache_stats_shape(env):
    stats = await cache.cache_stats("p1")
    assert set(stats) >= {"hits", "misses", "stale_serves", "avoided_calls", "tools", "analytics"}
