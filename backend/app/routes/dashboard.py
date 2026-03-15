"""Internal dashboard endpoints: REST snapshot + real-time WebSocket stream."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.schemas import build_snapshot, snapshot_to_dashboard, DashboardSnapshot
from app.dependencies import get_event_log, get_connection_manager
from app.event_log import EventLog
from app.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/dashboard/snapshot", response_model=DashboardSnapshot)
async def dashboard_snapshot(
    connection_manager: ConnectionManager = Depends(get_connection_manager),
    event_log: EventLog = Depends(get_event_log),
) -> DashboardSnapshot:
    """Return the full current state + recent event history."""
    raw = await connection_manager.snapshot()
    return snapshot_to_dashboard(raw, events=event_log.get_events())


@router.websocket("/dashboard/stream")
async def dashboard_stream(
    websocket: WebSocket,
    connection_manager: ConnectionManager = Depends(get_connection_manager),
    event_log: EventLog = Depends(get_event_log),
) -> None:
    """Real-time dashboard stream.

    On connect  → SNAPSHOT with full state + buffered event history.
    On any connection-manager state change → EVENT message then a fresh SNAPSHOT,
                                             pushed by the EventLog listener.
    On signal events (offer/answer/candidate) → EVENT only.
    """
    await websocket.accept()

    # Send initial full state so the UI is populated immediately
    raw = await connection_manager.snapshot()
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
