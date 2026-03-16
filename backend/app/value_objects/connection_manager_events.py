"""Typed value objects emitted by the ConnectionManager after every state change.

All are frozen dataclasses so they are immutable and hashable.
Listeners receive a ``ConnectionManagerEvent`` and can pattern-match on the type.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class RoomCreated:
    room_id: str


@dataclass(frozen=True)
class RoomDestroyed:
    room_id: str


@dataclass(frozen=True)
class PeerJoined:
    """REST join succeeded — peer slot assigned (new or reclaimed)."""
    room_id: str
    peer_id: str
    client_id: str
    reconnected: bool


@dataclass(frozen=True)
class PeerConnected:
    """WebSocket bound to a peer slot."""
    room_id: str
    peer_id: str
    reconnected: bool


@dataclass(frozen=True)
class PeerDisconnected:
    """WebSocket dropped; peer remains in room within the reconnect grace window."""
    room_id: str
    peer_id: str


@dataclass(frozen=True)
class PeerRemoved:
    """Peer fully removed from its room.

    ``cause`` is set by the caller:
      - ``"left"``           — explicit LEAVE message from the client
      - ``"evicted_stale"``  — heartbeat timeout
      - ``"evicted"``        — reconnect grace window expired
    """
    room_id: str
    peer_id: str
    cause: str


# Union type for exhaustive listener signatures
ConnectionManagerEvent = Union[
    RoomCreated,
    RoomDestroyed,
    PeerJoined,
    PeerConnected,
    PeerDisconnected,
    PeerRemoved,
]
