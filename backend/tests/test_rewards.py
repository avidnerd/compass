"""Deterministic scoring, levels, and reward idempotency."""
from app.services import rewards


def test_level_thresholds():
    assert rewards.level_threshold(1) == 50
    assert rewards.level_threshold(2) == 150
    assert rewards.level_for_xp(0) == 1
    assert rewards.level_for_xp(49) == 1
    assert rewards.level_for_xp(50) == 2
    assert rewards.level_for_xp(150) == 3


def test_focus_score_neutral_improvement_until_five_sessions():
    score = rewards.calculate_focus_score(
        active_seconds=1500, planned_seconds=1500, paused_seconds=0, total_seconds=1500,
        completion=1.0, prior_scores=[10, 20])
    # commitment=1, completion=1, continuity=1, improvement=0.5
    assert score == round(100 * (0.30 + 0.45 + 0.15 + 0.05))  # 95


def test_focus_score_uses_personal_percentile():
    prior = [50, 55, 60, 65, 70]
    high = rewards.calculate_focus_score(1500, 1500, 0, 1500, 1.0, prior)
    assert high == 100  # everything maxed and above own baseline
    low = rewards.calculate_focus_score(300, 1500, 600, 900, 0.0, prior)
    assert low < 30


def test_focus_score_clamps_commitment():
    over = rewards.calculate_focus_score(9000, 1500, 0, 9000, 1.0, [])
    assert over <= 100


def test_session_rewards_and_human_confirm_cap():
    r = rewards.session_rewards(90, "craft", human_confirmed=False)
    assert r["xp"] == 28 and r["care_points"] == 4
    assert r["stats"] == {"focus": 2, "craft": 2}
    rc = rewards.session_rewards(90, "craft", human_confirmed=True)
    assert rc["stats"] == {"focus": 1, "craft": 1}  # capped at +1
    assert rc["xp"] == round(28 * 0.8)


def test_primary_stat_mapping():
    ev = [{"source": "github"}, {"source": "github"}, {"source": "gmail"}]
    assert rewards.primary_stat_for_evidence(ev) == "craft"
    assert rewards.primary_stat_for_evidence([]) is None


async def test_apply_rewards_idempotent(env):
    from conftest import create_profile
    data = await create_profile(env.client)
    profile_id = data["profile"]["id"]
    resp = await env.client.post("/api/v1/character", json={"name": "Pip"})
    assert resp.status_code == 201
    first = await rewards.apply_rewards(profile_id, "session:abc", 30, 2, {"focus": 1}, "test")
    assert first is not None and first["xp"] == 30
    dup = await rewards.apply_rewards(profile_id, "session:abc", 30, 2, {"focus": 1}, "test")
    assert dup is None  # duplicate source event grants nothing
    ch = (await env.client.get("/api/v1/character")).json()["data"]
    assert ch["xp"] == 30 and ch["care_points"] == 5  # 3 starting + 2
    assert ch["stat_focus"] == 2
