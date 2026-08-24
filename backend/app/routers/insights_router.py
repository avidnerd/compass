"""Insights: ported analytics + Compass-native metrics."""
from fastapi import APIRouter, Request

from ..api import CurrentProfile, envelope
from ..services import insights

router = APIRouter()


def _q(request: Request) -> tuple[int, bool]:
    weeks = int(request.query_params.get("weeks", "8"))
    refresh = request.query_params.get("refresh", "false").lower() in ("1", "true")
    return max(1, min(weeks, 26)), refresh


@router.get("/analytics/summary")
async def summary(request: Request, profile: dict = CurrentProfile):
    weeks, refresh = _q(request)
    data, metas = await insights.summary(profile, weeks=weeks, refresh=refresh)
    return envelope(data, request, *metas)


@router.get("/analytics/baseline")
async def baseline(request: Request, profile: dict = CurrentProfile):
    return envelope(await insights.baseline(profile["id"]), request)


@router.get("/analytics/timeline")
async def timeline(request: Request, profile: dict = CurrentProfile):
    weeks, refresh = _q(request)
    data, metas = await insights.trends(profile, weeks=weeks, refresh=refresh)
    return envelope(data, request, *metas)


@router.get("/analytics/calendar")
async def calendar(request: Request, profile: dict = CurrentProfile):
    weeks, refresh = _q(request)
    data, metas = await insights.calendar_load(profile, weeks=weeks, refresh=refresh)
    return envelope(data, request, *metas)


@router.get("/analytics/documents")
async def documents(request: Request, profile: dict = CurrentProfile):
    _, refresh = _q(request)
    data, metas = await insights.document_activity(profile, refresh=refresh)
    return envelope(data, request, *metas)


@router.get("/analytics/email")
async def email(request: Request, profile: dict = CurrentProfile):
    weeks, refresh = _q(request)
    data, metas = await insights.email_activity(profile, weeks=weeks, refresh=refresh)
    return envelope(data, request, *metas)


@router.get("/analytics/meet")
async def meet(request: Request, profile: dict = CurrentProfile):
    weeks, refresh = _q(request)
    data, metas = await insights.meet_activity(profile, weeks=weeks, refresh=refresh)
    return envelope(data, request, *metas)


@router.get("/analytics/github")
async def github(request: Request, profile: dict = CurrentProfile):
    weeks, refresh = _q(request)
    data, metas = await insights.github_activity(profile, weeks=weeks, refresh=refresh)
    return envelope(data, request, *metas)


@router.get("/analytics/collaboration")
async def collaboration(request: Request, profile: dict = CurrentProfile):
    weeks, refresh = _q(request)
    data, metas = await insights.collaboration(profile, weeks=weeks, refresh=refresh)
    return envelope(data, request, *metas)


@router.get("/analytics/sessions")
async def sessions(request: Request, profile: dict = CurrentProfile):
    return envelope(await insights.session_history(profile["id"]), request)


@router.get("/analytics/stat-growth")
async def stat_growth(request: Request, profile: dict = CurrentProfile):
    return envelope(await insights.stat_growth(profile["id"]), request)


@router.get("/analytics/verifications")
async def verifications(request: Request, profile: dict = CurrentProfile):
    return envelope(await insights.verification_history(profile["id"]), request)


@router.get("/telemetry/freshness")
async def freshness(request: Request, profile: dict = CurrentProfile):
    return envelope(await insights.freshness(profile["id"]), request)
