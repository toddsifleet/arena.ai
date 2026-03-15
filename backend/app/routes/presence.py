"""WebSocket endpoint for real-time room presence events.

Clients connect here (separate from PeerJS signaling) to receive PRESENCE
messages immediately when a peer joins, leaves, or disconnects.
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.dependencies import get_registry
from app.connection_manager import ConnectionManager, send_json
from app.schemas import PresenceMessage, PresencePayload

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

    # Send the current snapshot so the client doesn't need to poll for initial state.
    for peer in await registry.list_peers(room):
        if await registry.get_ws(peer.peer_id):
            await send_json(
                websocket,
                PresenceMessage(
                    payload=PresencePayload(kind="reconnected", peer_id=peer.peer_id, room_id=room)
                ),
            )

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("presence_ws error for room %s", room)
    finally:
        await registry.remove_presence_sub(room, websocket)
