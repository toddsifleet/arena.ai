"""Internal dashboard endpoints: REST snapshot + real-time WebSocket stream."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.schemas import build_snapshot
from app.dependencies import get_event_log, get_registry
from app.event_log import EventLog
from app.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/dashboard/snapshot")
async def dashboard_snapshot(
    registry: ConnectionManager = Depends(get_registry),
    event_log: EventLog = Depends(get_event_log),
) -> dict:
    """Return the full current state + recent event history."""
    raw = await registry.snapshot()
    raw["events"] = [e.model_dump() for e in event_log.get_events()]
    return raw


@router.websocket("/dashboard/stream")
async def dashboard_stream(
    websocket: WebSocket,
    registry: ConnectionManager = Depends(get_registry),
    event_log: EventLog = Depends(get_event_log),
) -> None:
    """Real-time dashboard stream.

    On connect  → SNAPSHOT with full state + buffered event history.
    On any registry state change → EVENT message then a fresh SNAPSHOT,
                                   pushed by the EventLog listener.
    On signal events (offer/answer/candidate) → EVENT only.
    """
    await websocket.accept()

    # Send initial full state so the UI is populated immediately
    raw = await registry.snapshot()
    initial = build_snapshot(raw, events=event_log.get_events())
    try:
        await websocket.send_text(initial)
    except Exception:
        return

    event_log.subscribe(websocket)
    try:
        # Discard any client messages; just keep the connection alive
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("dashboard stream error")
    finally:
        event_log.unsubscribe(websocket)
