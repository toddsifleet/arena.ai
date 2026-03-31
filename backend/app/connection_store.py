"""Pure in-memory state store for rooms and peers — no WebSocket knowledge."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid

from app.schemas import PeerSnapDict, SnapshotData, SnapshotStats
from app.value_objects import (
    AlreadyConnected,
    JoinResult,
    PeerInfo,
    PeerState,
    RoomFull,
    RoomNotFound,
)

logger = logging.getLogger(__name__)


def _generate_id() -> str:
    return str(uuid.uuid4())


class ConnectionStore:
    """Thread-safe in-memory store for room and peer state.

    Tracks which peers belong to which rooms, heartbeat timestamps, and
    reconnect-grace windows.  Has no knowledge of WebSockets or event
    dispatch — those concerns belong to ``ConnectionManager``.

    **Restart caveat (intentional, omitted for brevity):** all state lives in
    process memory.  A restart or crash wipes every room and peer mapping —
    connected clients will need to rejoin.  The interface is deliberately
    abstracted so a Redis-backed implementation can be dropped in with no
    changes to callers; see DECISIONS.md for the full discussion of durable
    and stateless-restart alternatives.
    """

    def __init__(self) -> None:
        self._room_to_peers: dict[str, set[str]] = {}
        self._room_created_at: dict[str, float] = {}
        self._room_to_client_peer: dict[str, dict[str, str]] = {}
        self._peers: dict[str, PeerState] = {}
        self._lock = asyncio.Lock()

    async def create_room(self) -> str:
        room_id = _generate_id()
        async with self._lock:
            self._room_to_peers[room_id] = set()
            self._room_created_at[room_id] = time.monotonic()
        return room_id

    async def room_exists(self, room_id: str) -> bool:
        async with self._lock:
            return room_id in self._room_to_peers

    async def list_room_ids(self) -> list[str]:
        async with self._lock:
            return list(self._room_to_peers.keys())

    async def join_room(self, room_id: str, client_id: str | None = None) -> JoinResult:
        """Add a peer to a room.

        Raises RoomNotFound, RoomFull, or AlreadyConnected.
        """
        cid = (client_id or "").strip() or _generate_id()
        async with self._lock:
            if room_id not in self._room_to_peers:
                raise RoomNotFound(room_id)

            client_map = self._room_to_client_peer.setdefault(room_id, {})

            if cid in client_map:
                peer_id = client_map[cid]
                peer = self._peers.get(peer_id)
                if peer and peer.connected:
                    raise AlreadyConnected(peer_id)
                if not peer:
                    peer_id = _generate_id()
                    self._room_to_peers[room_id].add(peer_id)
                    client_map[cid] = peer_id
                    self._peers[peer_id] = PeerState(peer_id=peer_id, room_id=room_id, client_id=cid)
                    result = JoinResult(
                        room_id=room_id, peer_id=peer_id, client_id=cid, reconnected=False
                    )
                else:
                    result = JoinResult(
                        room_id=room_id, peer_id=peer_id, client_id=cid, reconnected=True
                    )
            elif len(client_map) >= 2:
                raise RoomFull(room_id)
            else:
                peer_id = _generate_id()
                self._room_to_peers[room_id].add(peer_id)
                client_map[cid] = peer_id
                self._peers[peer_id] = PeerState(peer_id=peer_id, room_id=room_id, client_id=cid)
                result = JoinResult(
                    room_id=room_id, peer_id=peer_id, client_id=cid, reconnected=False
                )

        return result

    async def remove_room_if_empty(self, room_id: str) -> bool:
        """Remove a room only if it is currently empty. Returns True if removed."""
        async with self._lock:
            peers = self._room_to_peers.get(room_id)
            if peers is not None and not peers:
                del self._room_to_peers[room_id]
                self._room_created_at.pop(room_id, None)
                self._room_to_client_peer.pop(room_id, None)
                return True
        return False

    async def get_peer_room(self, peer_id: str) -> str | None:
        async with self._lock:
            peer = self._peers.get(peer_id)
            return peer.room_id if peer else None

    async def get_other_peers_in_room(self, room_id: str, exclude_peer_id: str) -> list[str]:
        async with self._lock:
            peers = self._room_to_peers.get(room_id)
            if not peers:
                return []
            return [p for p in peers if p != exclude_peer_id]

    async def list_peers(self, room_id: str) -> list[PeerInfo]:
        async with self._lock:
            peer_ids = self._room_to_peers.get(room_id)
            if peer_ids is None:
                return []
            return [
                PeerInfo(
                    peer_id=pid,
                    client_id=peer.client_id if (peer := self._peers.get(pid)) else "",
                    connected=peer.connected if peer else False,
                )
                for pid in peer_ids
            ]

    async def mark_peer_connected(self, peer_id: str) -> bool:
        """Record that a peer's WebSocket is now active.

        Clears the reconnect-grace timer and records a fresh heartbeat.
        Returns True if the peer was previously in the reconnect-grace window.
        """
        async with self._lock:
            peer = self._peers.get(peer_id)
            if not peer:
                return False
            was_reconnecting = peer.disconnected_at is not None
            peer.disconnected_at = None
            peer.connected = True
            peer.last_heartbeat_at = time.monotonic()
            return was_reconnecting

    async def mark_peer_disconnected(self, peer_id: str) -> str | None:
        """Record that a peer's WebSocket has dropped; keep the slot for reconnect.

        Returns room_id if the peer was in a room, else None.
        """
        async with self._lock:
            peer = self._peers.get(peer_id)
            if not peer:
                return None
            peer.connected = False
            peer.last_heartbeat_at = None
            peer.disconnected_at = time.monotonic()
            return peer.room_id

    async def is_peer_reconnecting(self, peer_id: str) -> bool:
        async with self._lock:
            peer = self._peers.get(peer_id)
            return bool(peer and peer.disconnected_at is not None)

    async def remove_peer(self, peer_id: str) -> tuple[str | None, bool]:
        """Fully remove a peer from its room.

        Returns (room_id, room_destroyed).  Caller must hold no lock.
        """
        async with self._lock:
            return self._remove_peer(peer_id)

    def _remove_peer(self, peer_id: str) -> tuple[str | None, bool]:
        """Inner removal — caller must hold ``_lock``."""
        peer = self._peers.pop(peer_id, None)
        if not peer:
            return None, False
        room_id = peer.room_id
        client_id = peer.client_id
        room_destroyed = False
        if room_id:
            peers = self._room_to_peers.get(room_id)
            if peers is not None:
                peers.discard(peer_id)
                if not peers:
                    del self._room_to_peers[room_id]
                    self._room_created_at.pop(room_id, None)
                    room_destroyed = True
            client_map = self._room_to_client_peer.get(room_id)
            if client_map is not None:
                if client_id is not None:
                    client_map.pop(client_id, None)
                # Always wipe the map when the room is gone to avoid a stale entry
                # if client_id was somehow missing from the peer store.
                if room_destroyed or not client_map:
                    self._room_to_client_peer.pop(room_id, None)
        return room_id, room_destroyed

    async def touch_heartbeat(self, peer_id: str) -> None:
        async with self._lock:
            peer = self._peers.get(peer_id)
            if peer and peer.last_heartbeat_at is not None:
                peer.last_heartbeat_at = time.monotonic()

    async def get_stale_peer_ids(self, timeout_seconds: float) -> list[str]:
        async with self._lock:
            now = time.monotonic()
            return [
                pid for pid, peer in self._peers.items()
                if peer.last_heartbeat_at is not None and now - peer.last_heartbeat_at > timeout_seconds
            ]

    async def get_peers_past_reconnect_grace(self, grace_seconds: float) -> list[str]:
        async with self._lock:
            now = time.monotonic()
            return [
                pid for pid, peer in self._peers.items()
                if peer.disconnected_at is not None and now - peer.disconnected_at > grace_seconds
            ]

    async def get_empty_rooms_past_ttl(self, ttl_seconds: float) -> list[str]:
        async with self._lock:
            now = time.monotonic()
            return [
                room_id
                for room_id, peers in self._room_to_peers.items()
                if not peers
                and now - self._room_created_at.get(room_id, now) > ttl_seconds
            ]

    async def snapshot(self) -> SnapshotData:
        async with self._lock:
            now = time.monotonic()
            rooms: dict[str, list[PeerSnapDict]] = {}
            for room_id, peer_ids in self._room_to_peers.items():
                peers: list[PeerSnapDict] = []
                for pid in peer_ids:
                    peer = self._peers.get(pid)
                    if not peer:
                        continue
                    last_hb = peer.last_heartbeat_at
                    disc_at = peer.disconnected_at
                    peers.append(
                        PeerSnapDict(
                            peer_id=pid,
                            client_id=peer.client_id,
                            connected=peer.connected,
                            last_heartbeat_ago=(
                                round(now - last_hb, 1) if last_hb is not None else None
                            ),
                            disconnected_ago=(
                                round(now - disc_at, 1) if disc_at is not None else None
                            ),
                        )
                    )
                rooms[room_id] = peers
            stats = SnapshotStats(
                total_rooms=len(self._room_to_peers),
                connected_peers=sum(1 for peer in self._peers.values() if peer.connected),
                disconnected_peers=sum(
                    1 for peer in self._peers.values() if peer.disconnected_at is not None
                ),
                total_peers=len(self._peers),
            )
            return SnapshotData(rooms=rooms, stats=stats)

    async def shutdown(self) -> None:
        async with self._lock:
            self._room_to_peers.clear()
            self._room_created_at.clear()
            self._room_to_client_peer.clear()
            self._peers.clear()
        logger.info("ConnectionStore shutdown complete")
