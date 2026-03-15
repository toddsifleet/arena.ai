"""REST API request/response schemas and WebSocket wire-format models."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CreateRoomResponse(BaseModel):
    room_id: str


class JoinRoomResponse(BaseModel):
    room_id: str
    peer_id: str
    client_id: str
    signaling_path: str = "/peerjs"


class EventPayload(BaseModel):
    id: int
    type: str
    data: dict[str, Any]
    timestamp: float

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class DashboardEvent(BaseModel):
    type: Literal["EVENT"] = "EVENT"
    event: EventPayload


class PeerSnap(BaseModel):
    peer_id: str
    client_id: str
    connected: bool
    last_heartbeat_ago: float | None
    disconnected_ago: float | None


class RoomSnap(BaseModel):
    room_id: str
    peers: list[PeerSnap]


class StatsSnap(BaseModel):
    total_rooms: int
    connected_peers: int
    disconnected_peers: int
    total_peers: int


class DashboardSnapshot(BaseModel):
    type: Literal["SNAPSHOT"] = "SNAPSHOT"
    rooms: list[RoomSnap]
    stats: StatsSnap
    events: list[EventPayload] | None = None


def build_snapshot(raw: dict[str, Any], events: list[EventPayload] | None = None) -> str:
    """Convert the raw dict from ``ConnectionManager.snapshot()`` into a serialised ``DashboardSnapshot``."""
    rooms = [
        RoomSnap(
            room_id=room_id,
            peers=[PeerSnap(**p) for p in peers],
        )
        for room_id, peers in raw["rooms"].items()
    ]
    snap = DashboardSnapshot(
        rooms=rooms,
        stats=StatsSnap(**raw["stats"]),
        events=events,
    )
    return snap.model_dump_json()


class ErrorPayload(BaseModel):
    msg: str


class ErrorMessage(BaseModel):
    type: Literal["ERROR"] = "ERROR"
    payload: ErrorPayload


class OpenPayload(BaseModel):
    id: str


class OpenMessage(BaseModel):
    type: Literal["OPEN"] = "OPEN"
    payload: OpenPayload


class HeartbeatMessage(BaseModel):
    type: Literal["HEARTBEAT"] = "HEARTBEAT"


class PresencePayload(BaseModel):
    kind: Literal["joined", "reconnected", "disconnected", "left"]
    peer_id: str
    room_id: str


class PresenceMessage(BaseModel):
    type: Literal["PRESENCE"] = "PRESENCE"
    payload: PresencePayload


class IncomingSignalingEnvelope(BaseModel):
    """Minimal incoming WS envelope before routing by message type."""

    model_config = ConfigDict(extra="allow")

    type: str = ""
    dst: str | None = None
    payload: dict[str, Any] | None = None

    @property
    def normalized_type(self) -> str:
        return self.type.strip().upper()

    @property
    def resolved_dst(self) -> str | None:
        direct = (self.dst or "").strip()
        if direct:
            return direct
        payload_dst = self.payload.get("dst") if self.payload else None
        if isinstance(payload_dst, str):
            payload_dst = payload_dst.strip()
            if payload_dst:
                return payload_dst
        return None


class SignalRelayMessage(BaseModel):
    """Validated signaling message that can be forwarded peer-to-peer."""

    model_config = ConfigDict(extra="allow")

    type: Literal["OFFER", "ANSWER", "CANDIDATE"]
    src: str
    dst: str
    payload: dict[str, Any] = Field(default_factory=dict)
