"""WebSocket signaling endpoint (PeerJS-compatible for 1:1 calls)."""
from __future__ import annotations

import json
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
_WS_ALREADY_CLOSED_ERROR = 'Cannot call "send" once a close message has been sent.'


async def _close_websocket_safely(
    websocket: WebSocket,
    *,
    peer_id: str | None,
    context: str,
) -> None:
    """Best-effort close that tolerates common websocket close races."""
    try:
        await websocket.close()
    except RuntimeError as exc:
        if _WS_ALREADY_CLOSED_ERROR in str(exc):
            logger.info(
                "websocket already closed during %s for peer %s",
                context,
                peer_id or "<unknown>",
            )
            return
        logger.exception(
            "unexpected runtime error while closing websocket during %s for peer %s",
            context,
            peer_id or "<unknown>",
        )
    except WebSocketDisconnect:
        logger.info(
            "websocket disconnected before server close during %s for peer %s",
            context,
            peer_id or "<unknown>",
        )
    except Exception:
        logger.exception(
            "failed to close websocket during %s for peer %s",
            context,
            peer_id or "<unknown>",
        )


def _signal_event_data(
    room_id: str,
    src: str,
    dst: str,
    payload: dict[str, object] | None,
) -> dict[str, str | bool]:
    data: dict[str, str | bool] = {"room_id": room_id, "src": src, "dst": dst}
    if not payload:
        return data

    # Keep structured payload for deep dashboard inspection while preserving
    # string-only event values used by EventPayload.
    data["payload_json"] = json.dumps(payload)

    candidate = payload.get("candidate")
    if isinstance(candidate, str):
        data["candidate"] = candidate

    sdp_mid = payload.get("sdpMid")
    if isinstance(sdp_mid, str):
        data["sdp_mid"] = sdp_mid

    sdp_mline_index = payload.get("sdpMLineIndex")
    if isinstance(sdp_mline_index, (int, float, str)):
        data["sdp_mline_index"] = str(sdp_mline_index)

    return data


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
        await _close_websocket_safely(websocket, peer_id=None, context="missing id rejection")
        return

    room_id = await connection_manager.peer_in_room(peer_id)
    if not room_id:
        await send_json(
            websocket,
            ErrorMessage(payload=ErrorPayload(msg="Peer not in room; join via REST first")),
        )
        await _close_websocket_safely(
            websocket,
            peer_id=peer_id,
            context="unknown peer rejection",
        )
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
                    _signal_event_data(room_id, peer_id, dst, incoming.payload),
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
