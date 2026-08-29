"""Focus rooms. REST mutates; WebSockets deliver events."""
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from ..api import CurrentProfile, envelope
from ..services import demo_multiplayer
from ..services import parties as party_service

router = APIRouter()


class CreatePartyBody(BaseModel):
    name: str = ""
    theme: str | None = None
    simulated_player_ids: list[str] = Field(default_factory=list, max_length=5)


class JoinBody(BaseModel):
    code: str


@router.post("/parties", status_code=201)
async def create_party(body: CreatePartyBody, request: Request, profile: dict = CurrentProfile):
    return envelope(await party_service.create_party(
        profile, body.name, body.theme, body.simulated_player_ids), request)


@router.get("/multiplayer/players")
async def multiplayer_players(request: Request, profile: dict = CurrentProfile):
    return envelope(demo_multiplayer.list_players(), request)


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
