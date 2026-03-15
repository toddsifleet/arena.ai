"""Room creation and join (REST). Unguessable room IDs; max 2 peers per room."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_connection_manager
from app.schemas import CreateRoomResponse, JoinRoomResponse
from app.value_objects import AlreadyConnected, RoomFull, RoomNotFound
from app.connection_manager import ConnectionManager
from app.settings import settings

router = APIRouter()


@router.post("", response_model=CreateRoomResponse)
async def create_room(connection_manager: ConnectionManager = Depends(get_connection_manager)) -> CreateRoomResponse:
    room_id = await connection_manager.create_room()
    return CreateRoomResponse(room_id=room_id)


@router.get("/{room_id}/join", response_model=JoinRoomResponse)
async def join_room(
    room_id: UUID,
    client_id: str | None = None,
    connection_manager: ConnectionManager = Depends(get_connection_manager),
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


@router.get("/{room_id}/peers")
async def list_peers(
    room_id: UUID,
    connection_manager: ConnectionManager = Depends(get_connection_manager),
) -> dict:
    peers = await connection_manager.list_peers(str(room_id))
    return {
        "peers": [
            {"id": p.peer_id, "client_id": p.client_id, "connected": p.connected}
            for p in peers
        ],
    }
