"""Domain value objects, exceptions, and signaling types."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


# --- Domain value objects ---


@dataclass(frozen=True, slots=True)
class JoinResult:
    """Returned by Registry.join_room on success."""

    room_id: str
    peer_id: str
    client_id: str
    reconnected: bool


@dataclass(frozen=True, slots=True)
class PeerInfo:
    """Snapshot of a peer's state within a room."""

    peer_id: str
    client_id: str
    connected: bool


# --- Domain exceptions ---


class RoomNotFound(Exception):
    pass


class RoomFull(Exception):
    pass


class AlreadyConnected(Exception):
    pass


# --- PeerJS-compatible signaling types ---


class SignalingType(str, Enum):
    OPEN = "OPEN"
    HEARTBEAT = "HEARTBEAT"
    OFFER = "OFFER"
    ANSWER = "ANSWER"
    CANDIDATE = "CANDIDATE"
    LEAVE = "LEAVE"
    ERROR = "ERROR"


class PresenceKind(str, Enum):
    JOINED = "joined"
    LEFT = "left"
    DISCONNECTED = "disconnected"
    RECONNECTED = "reconnected"
