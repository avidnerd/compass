"""Battles and parties. REST mutates; WebSockets deliver events."""
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from ..api import CurrentProfile, envelope, idempotent
from ..services import battles as battle_service
from ..services import demo_multiplayer
from ..services import parties as party_service

router = APIRouter()


class CreateBattleBody(BaseModel):
    minutes: int = 25
    demo: bool = False
    opponent_ids: list[str] = Field(default_factory=list, max_length=3)


@router.post("/battles", status_code=201)
async def create_battle(body: CreateBattleBody, request: Request, profile: dict = CurrentProfile):
    async def handler():
        return await battle_service.create_battle(profile, body.minutes, body.demo, body.opponent_ids)
    return envelope(await idempotent(request, profile["id"], "POST /battles", handler), request)


class JoinBody(BaseModel):
    code: str = Field(min_length=4, max_length=10)


@router.post("/battles:join")
async def join_battle(body: JoinBody, request: Request, profile: dict = CurrentProfile):
    return envelope(await battle_service.join_battle(profile, body.code), request)


@router.get("/battles/{battle_id}")
async def get_battle(battle_id: str, request: Request, profile: dict = CurrentProfile):
    await battle_service._require_player(battle_id, profile["id"])
    return envelope(await battle_service.public_battle(battle_id, profile["id"]), request)


class ReadyBody(BaseModel):
    ready: bool = True
    subgoal_id: str | None = None


@router.post("/battles/{battle_id}:ready")
async def ready(battle_id: str, body: ReadyBody, request: Request, profile: dict = CurrentProfile):
    return envelope(await battle_service.set_ready(profile, battle_id, body.ready, body.subgoal_id),
                    request)


@router.post("/battles/{battle_id}:start")
async def start_battle(battle_id: str, request: Request, profile: dict = CurrentProfile):
    return envelope(await battle_service.start_battle(profile, battle_id), request)


@router.post("/battles/{battle_id}:leave")
async def leave_battle(battle_id: str, request: Request, profile: dict = CurrentProfile):
    return envelope(await battle_service.leave_battle(profile, battle_id), request)


@router.post("/battles/{battle_id}:cancel")
async def cancel_battle(battle_id: str, request: Request, profile: dict = CurrentProfile):
    return envelope(await battle_service.cancel_battle(profile, battle_id), request)


@router.get("/battles/{battle_id}/results")
async def battle_results(battle_id: str, request: Request, profile: dict = CurrentProfile):
    return envelope(await battle_service.battle_results(profile["id"], battle_id), request)


# ----------------------------------------------------------------- parties

class CreatePartyBody(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    theme: str | None = None
    simulated_player_ids: list[str] = Field(default_factory=list, max_length=5)


@router.post("/parties", status_code=201)
async def create_party(body: CreatePartyBody, request: Request, profile: dict = CurrentProfile):
    return envelope(await party_service.create_party(
        profile, body.name, body.theme, body.simulated_player_ids), request)


@router.get("/multiplayer/players")
async def multiplayer_players(request: Request, profile: dict = CurrentProfile):
    return envelope(demo_multiplayer.list_players(), request)


@router.get("/leaderboards")
async def leaderboards(request: Request, profile: dict = CurrentProfile):
    return envelope(await demo_multiplayer.leaderboards(profile), request)


@router.post("/parties:join")
async def join_party(body: JoinBody, request: Request, profile: dict = CurrentProfile):
    return envelope(await party_service.join_party(profile, body.code), request)


@router.get("/parties")
async def list_parties(request: Request, profile: dict = CurrentProfile):
    return envelope(await party_service.list_parties(profile["id"]), request)


@router.get("/parties/{party_id}")
async def get_party(party_id: str, request: Request, profile: dict = CurrentProfile):
    await party_service._require_member(party_id, profile["id"])
    return envelope(await party_service.public_party(party_id), request)


@router.patch("/parties/{party_id}")
async def patch_party(party_id: str, request: Request, profile: dict = CurrentProfile):
    body = await request.json()
    return envelope(await party_service.patch_party(profile, party_id, body or {}), request)


@router.post("/parties/{party_id}:leave")
async def leave_party(party_id: str, request: Request, profile: dict = CurrentProfile):
    await party_service.leave_party(profile, party_id)
    return envelope({"left": True}, request)


class EmoteBody(BaseModel):
    emote: str


@router.post("/parties/{party_id}/emotes")
async def emote(party_id: str, body: EmoteBody, request: Request, profile: dict = CurrentProfile):
    await party_service.send_emote(profile, party_id, body.emote)
    return envelope({"sent": True}, request)


class BossBody(BaseModel):
    difficulty: str = "standard"


@router.post("/parties/{party_id}/boss-encounters", status_code=201)
async def start_boss(party_id: str, body: BossBody, request: Request, profile: dict = CurrentProfile):
    return envelope(await party_service.start_boss_encounter(profile, party_id, body.difficulty),
                    request)


@router.get("/parties/{party_id}/boss-encounters/{encounter_id}")
async def get_boss(party_id: str, encounter_id: str, request: Request, profile: dict = CurrentProfile):
    return envelope(await party_service.boss_encounter(profile["id"], party_id, encounter_id), request)


@router.get("/parties/{party_id}/contributions")
async def get_contributions(party_id: str, request: Request, profile: dict = CurrentProfile):
    return envelope(await party_service.contributions(profile["id"], party_id), request)
