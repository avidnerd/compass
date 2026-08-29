"""Canvas calendar feed: link it, read upcoming assignments, import them as quests.

Read-only throughout — the only writes are to Compass's own local database.
"""
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from ..api import CurrentProfile, envelope, idempotent
from ..services import canvas as canvas_service

router = APIRouter(prefix="/canvas", tags=["canvas"])


class LinkBody(BaseModel):
    feed_url: str = Field(min_length=1, max_length=2000)


@router.get("")
async def get_overview(request: Request, refresh: bool = False, profile: dict = CurrentProfile):
    return envelope(await canvas_service.overview(profile, force=refresh), request)


@router.get("/status")
async def get_status(request: Request, profile: dict = CurrentProfile):
    return envelope(await canvas_service.public_link(profile["id"]), request)


@router.post("/link")
async def create_link(body: LinkBody, request: Request, profile: dict = CurrentProfile):
    return envelope(await canvas_service.link(profile["id"], body.feed_url), request)


@router.delete("/link")
async def delete_link(request: Request, profile: dict = CurrentProfile):
    return envelope(await canvas_service.unlink(profile["id"]), request)


@router.get("/assignments")
async def get_assignments(request: Request, refresh: bool = False, days: int = 60,
                          profile: dict = CurrentProfile):
    return envelope(await canvas_service.assignments(
        profile, force=refresh, days=max(1, min(days, 365))), request)


class ImportBody(BaseModel):
    source_keys: list[str] = Field(min_length=1, max_length=20)
    plan: bool = True


@router.post("/quests:import", status_code=201)
async def import_quests(body: ImportBody, request: Request, profile: dict = CurrentProfile):
    async def handler():
        return await canvas_service.import_assignments(profile, body.source_keys, plan=body.plan)
    result = await idempotent(request, profile["id"], "POST /canvas/quests:import", handler)
    return envelope(result, request)
