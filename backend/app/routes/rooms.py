"""Room creation and join (REST). Unguessable room IDs; max 2 peers per room."""
from __future__ import annotations

from uuid import UUID
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from app.dependencies import get_connection_manager, get_event_log
from app.schemas import (
    CreateRoomResponse,
    JoinRoomResponse,
    ListPeersResponse,
    PeerListItem,
    TelemetrySelectedPairRequest,
)
from app.value_objects import AlreadyConnected, RoomFull, RoomNotFound
from app.connection_manager import ConnectionManager
from app.event_log import EventLog
from app.settings import settings

router = APIRouter()
ConnectionManagerDep = Annotated[ConnectionManager, Depends(get_connection_manager)]
EventLogDep = Annotated[EventLog, Depends(get_event_log)]


@router.post("", response_model=CreateRoomResponse)
async def create_room(connection_manager: ConnectionManagerDep) -> CreateRoomResponse:
    room_id = await connection_manager.create_room()
    return CreateRoomResponse(room_id=room_id)


@router.get("/{room_id}/join", response_model=JoinRoomResponse)
async def join_room(
    room_id: UUID,
    connection_manager: ConnectionManagerDep,
    client_id: str | None = None,
) -> JoinRoomResponse:
    try:
        result = await connection_manager.join_room(str(room_id), client_id)
    except RoomNotFound as exc:
        raise HTTPException(status_code=404, detail="room_not_found") from exc
    except RoomFull as exc:
        raise HTTPException(status_code=403, detail="room_full") from exc
    except AlreadyConnected as exc:
        raise HTTPException(status_code=409, detail="already_connected") from exc

    return JoinRoomResponse(
        room_id=result.room_id,
        peer_id=result.peer_id,
        client_id=result.client_id,
        signaling_path=settings.signaling_path,
    )


@router.get("/{room_id}/peers", response_model=ListPeersResponse)
async def list_peers(
    room_id: UUID,
    connection_manager: ConnectionManagerDep,
) -> ListPeersResponse:
    peers = await connection_manager.list_peers(str(room_id))
    return ListPeersResponse(
        peers=[PeerListItem(id=p.peer_id, client_id=p.client_id, connected=p.connected) for p in peers]
    )


@router.post("/{room_id}/telemetry", status_code=204, response_class=Response)
async def submit_telemetry(
    room_id: UUID,
    payload: TelemetrySelectedPairRequest,
    connection_manager: ConnectionManagerDep,
    event_log: EventLogDep,
) -> Response:
    resolved_room_id = await connection_manager.peer_in_room(payload.peer_id)
    if resolved_room_id != str(room_id):
        raise HTTPException(status_code=404, detail="peer_not_in_room")
    allowed_dsts = await connection_manager.get_other_peers_in_room(str(room_id), payload.peer_id)
    if payload.selected_pair.dst not in allowed_dsts:
        raise HTTPException(status_code=422, detail="invalid_dst")

    selected_pair = payload.selected_pair
    data: dict[str, str | bool] = {
        "room_id": str(room_id),
        "src": payload.peer_id,
        "dst": selected_pair.dst,
    }

    for key in (
        "local_candidate_type",
        "local_candidate_ip",
        "local_candidate_port",
        "local_candidate_protocol",
        "remote_candidate_type",
        "remote_candidate_ip",
        "remote_candidate_port",
        "remote_candidate_protocol",
        "pair_state",
        "round_trip_time_ms",
        "available_outgoing_bitrate",
        "bytes_sent",
        "bytes_received",
    ):
        value = getattr(selected_pair, key)
        if value is not None:
            data[key] = value

    await event_log.emit("telemetry.selected_pair", data)
    return Response(status_code=204)
