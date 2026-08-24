"""College OS: detect the Workspace structure, read the dashboard, import rows.

Read-only throughout — the only writes are to Compass's own local database.
"""
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from ..api import CurrentProfile, envelope, idempotent
from ..services import college as college_service

router = APIRouter(prefix="/college", tags=["college"])


@router.get("")
async def get_overview(request: Request, refresh: bool = False, profile: dict = CurrentProfile):
    return envelope(await college_service.overview(profile, force=refresh), request)


@router.get("/status")
async def get_status(request: Request, profile: dict = CurrentProfile):
    link = await college_service.get_link(profile["id"])
    return envelope(college_service.public_link(link), request)


@router.post("/detect")
async def run_detect(request: Request, profile: dict = CurrentProfile):
    return envelope(await college_service.detect(profile, force=True), request)


@router.get("/dashboard")
async def get_dashboard(request: Request, refresh: bool = False, profile: dict = CurrentProfile):
    return envelope(await college_service.read_dashboard(profile, force=refresh), request)


class ImportBody(BaseModel):
    source_keys: list[str] = Field(min_length=1, max_length=20)
    plan: bool = True


@router.post("/quests:import", status_code=201)
async def import_quests(body: ImportBody, request: Request, profile: dict = CurrentProfile):
    async def handler():
        return await college_service.import_rows(profile, body.source_keys, plan=body.plan)
    result = await idempotent(request, profile["id"], "POST /college/quests:import", handler)
    return envelope(result, request)


@router.delete("/link")
async def delete_link(request: Request, profile: dict = CurrentProfile):
    return envelope(await college_service.unlink(profile["id"]), request)
