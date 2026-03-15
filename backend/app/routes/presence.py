"""WebSocket endpoint for real-time room presence events.

Clients connect here (separate from PeerJS signaling) to receive PRESENCE
messages immediately when a peer joins, leaves, or disconnects.
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.dependencies import get_registry
from app.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/{room_id}/presence")
async def presence_ws(
    room_id: UUID,
    websocket: WebSocket,
    registry: ConnectionManager = Depends(get_registry),
) -> None:
    room = str(room_id)
    await websocket.accept()
    await registry.add_presence_sub(room, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("presence_ws error for room %s", room)
    finally:
        await registry.remove_presence_sub(room, websocket)
