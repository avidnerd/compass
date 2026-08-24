"""Authenticated WebSocket endpoint with replay + heartbeat."""
import asyncio
import contextlib
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from . import events
from .api import COOKIE_NAME
from .services import profiles as profile_service

logger = logging.getLogger("compass.ws")

router = APIRouter()

HEARTBEAT_SECONDS = 25


@router.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket):
    token = websocket.cookies.get(COOKIE_NAME)
    profile = await profile_service.profile_for_token(token) if token else None
    if profile is None:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    profile_id = profile["id"]

    after_raw = websocket.query_params.get("after")
    try:
        after = int(after_raw) if after_raw else 0
    except ValueError:
        after = 0

    queue = events.subscribe(profile_id)
    try:
        # Replay authorized missed events exactly once, then go live.
        for event in await events.replay(profile_id, after):
            await websocket.send_json(event)
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                await websocket.send_json(message)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception:
        logger.exception("[ws] connection error for profile %s", profile_id[:8])
    finally:
        events.unsubscribe(profile_id, queue)
        with contextlib.suppress(Exception):
            await websocket.close()
