"""WebSocket signaling endpoint (PeerJS-compatible for 1:1 calls)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.dependencies import get_event_log, get_connection_manager
from app.event_log import EventLog
from app.connection_manager import ConnectionManager, send_json
from app.schemas import (
    ErrorMessage,
    ErrorPayload,
    HeartbeatMessage,
    IncomingSignalingEnvelope,
    OpenMessage,
    OpenPayload,
    PresenceMessage,
    PresencePayload,
    SignalRelayMessage,
)
from app.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket(settings.signaling_path)
async def signaling_ws(
    websocket: WebSocket,
    id: str | None = Query(None, alias="id"),
    key: str | None = Query(None),
    connection_manager: ConnectionManager = Depends(get_connection_manager),
    event_log: EventLog = Depends(get_event_log),
) -> None:
    await websocket.accept()
    peer_id = (id or "").strip()
    if not peer_id:
        await send_json(websocket, ErrorMessage(payload=ErrorPayload(msg="Missing id")))
        await websocket.close()
        return

    room_id = await connection_manager.peer_in_room(peer_id)
    if not room_id:
        await send_json(
            websocket,
            ErrorMessage(payload=ErrorPayload(msg="Peer not in room; join via REST first")),
        )
        await websocket.close()
        return

    was_reconnecting = await connection_manager.register_peer_ws(peer_id, websocket)
    await send_json(websocket, OpenMessage(payload=OpenPayload(id=peer_id)))
    await connection_manager.notify_presence(peer_id, room_id, "reconnected" if was_reconnecting else "joined")

    # Tell this peer about everyone already connected so it doesn't have to wait for the poll
    for other_id in await connection_manager.get_other_peers_in_room(room_id, peer_id):
        if await connection_manager.get_ws(other_id):
            await send_json(
                websocket,
                PresenceMessage(
                    payload=PresencePayload(kind="reconnected", peer_id=other_id, room_id=room_id)
                ),
            )

    left_explicitly = False
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                incoming = IncomingSignalingEnvelope.model_validate_json(raw)
            except ValidationError:
                continue

            msg_type = incoming.normalized_type
            await connection_manager.touch_heartbeat(peer_id)

            if msg_type == "HEARTBEAT":
                await send_json(websocket, HeartbeatMessage())
            elif msg_type in ("OFFER", "ANSWER", "CANDIDATE"):
                dst = incoming.resolved_dst
                if not dst:
                    continue
                others = await connection_manager.get_other_peers_in_room(room_id, peer_id)
                if dst not in others:
                    continue
                dst_ws = await connection_manager.get_ws(dst)
                if dst_ws:
                    try:
                        relay = SignalRelayMessage.model_validate({
                            **incoming.model_dump(),
                            "type": msg_type,
                            "dst": dst,
                            "src": peer_id,
                        })
                    except ValidationError:
                        continue
                    await send_json(dst_ws, relay)
                # Signal events are not connection-manager state — emit directly
                await event_log.emit(
                    f"signal.{msg_type.lower()}",
                    {"room_id": room_id, "src": peer_id, "dst": dst},
                )
            elif msg_type == "LEAVE":
                left_explicitly = True
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("signaling error for peer %s", peer_id)
    finally:
        if left_explicitly:
            await connection_manager.notify_presence(peer_id, room_id, "left")
            await connection_manager.remove_peer_from_room(peer_id, cause="left")
        else:
            # Pass the specific websocket so unregister_peer_ws can detect if
            # the peer reconnected before this stale disconnect was processed.
            unregistered = await connection_manager.unregister_peer_ws(peer_id, websocket)
            if unregistered is not None:
                await connection_manager.notify_presence(peer_id, room_id, "disconnected")
