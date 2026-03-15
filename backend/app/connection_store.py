"""Pure in-memory state store for rooms and peers — no WebSocket knowledge."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid

from app.value_objects import AlreadyConnected, JoinResult, PeerInfo, RoomFull, RoomNotFound

logger = logging.getLogger(__name__)


def _generate_id() -> str:
    return str(uuid.uuid4())


class ConnectionStore:
    """Thread-safe in-memory store for room and peer state.

    Tracks which peers belong to which rooms, heartbeat timestamps, and
    reconnect-grace windows.  Has no knowledge of WebSockets or event
    dispatch — those concerns belong to ``ConnectionManager``.
    """

    def __init__(self) -> None:
        self._room_to_peers: dict[str, set[str]] = {}
        self._room_created_at: dict[str, float] = {}
        self._room_to_client_peer: dict[str, dict[str, str]] = {}
        self._peer_to_room: dict[str, str] = {}
        self._peer_to_client: dict[str, str] = {}
        self._connected_peers: set[str] = set()
        self._peer_last_heartbeat: dict[str, float] = {}
        self._peer_disconnected_at: dict[str, float] = {}
        self._lock = asyncio.Lock()

    # --- Room lifecycle ---

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
                if peer_id in self._connected_peers:
                    raise AlreadyConnected(peer_id)
                result = JoinResult(
                    room_id=room_id, peer_id=peer_id, client_id=cid, reconnected=True
                )
            elif len(client_map) >= 2:
                raise RoomFull(room_id)
            else:
                peer_id = _generate_id()
                self._room_to_peers[room_id].add(peer_id)
                client_map[cid] = peer_id
                self._peer_to_room[peer_id] = room_id
                self._peer_to_client[peer_id] = cid
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

    # --- Peer queries ---

    async def get_peer_room(self, peer_id: str) -> str | None:
        async with self._lock:
            return self._peer_to_room.get(peer_id)

    async def get_other_peers_in_room(self, room_id: str, exclude_peer_id: str) -> list[str]:
        async with self._lock:
            peers = self._room_to_peers.get(room_id)
            if not peers:
                return []
            return [p for p in peers if p != exclude_peer_id]

    async def list_peers(self, room_id: str) -> list[PeerInfo]:
        """Atomic snapshot of all peers in a room."""
        async with self._lock:
            peer_ids = self._room_to_peers.get(room_id)
            if peer_ids is None:
                return []
            return [
                PeerInfo(
                    peer_id=pid,
                    client_id=self._peer_to_client.get(pid, ""),
                    connected=pid in self._connected_peers,
                )
                for pid in peer_ids
            ]

    # --- Peer connection state ---

    async def mark_peer_connected(self, peer_id: str) -> bool:
        """Record that a peer's WebSocket is now active.

        Clears the reconnect-grace timer and records a fresh heartbeat.
        Returns True if the peer was previously in the reconnect-grace window.
        """
        async with self._lock:
            was_reconnecting = peer_id in self._peer_disconnected_at
            self._peer_disconnected_at.pop(peer_id, None)
            self._connected_peers.add(peer_id)
            self._peer_last_heartbeat[peer_id] = time.monotonic()
            return was_reconnecting

    async def mark_peer_disconnected(self, peer_id: str) -> str | None:
        """Record that a peer's WebSocket has dropped; keep the slot for reconnect.

        Returns room_id if the peer was in a room, else None.
        """
        async with self._lock:
            self._connected_peers.discard(peer_id)
            self._peer_last_heartbeat.pop(peer_id, None)
            room_id = self._peer_to_room.get(peer_id)
            if room_id:
                self._peer_disconnected_at[peer_id] = time.monotonic()
        return room_id

    async def is_peer_reconnecting(self, peer_id: str) -> bool:
        async with self._lock:
            return peer_id in self._peer_disconnected_at

    async def remove_peer(self, peer_id: str) -> tuple[str | None, bool]:
        """Fully remove a peer from its room.

        Returns (room_id, room_destroyed).  Caller must hold no lock.
        """
        async with self._lock:
            return self._remove_peer(peer_id)

    def _remove_peer(self, peer_id: str) -> tuple[str | None, bool]:
        """Inner removal — caller must hold ``_lock``."""
        room_id = self._peer_to_room.pop(peer_id, None)
        client_id = self._peer_to_client.pop(peer_id, None)
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
            if client_map and client_id is not None:
                client_map.pop(client_id, None)
                if not client_map:
                    del self._room_to_client_peer[room_id]
        self._connected_peers.discard(peer_id)
        self._peer_last_heartbeat.pop(peer_id, None)
        self._peer_disconnected_at.pop(peer_id, None)
        return room_id, room_destroyed

    # --- Heartbeat ---

    async def touch_heartbeat(self, peer_id: str) -> None:
        async with self._lock:
            if peer_id in self._peer_last_heartbeat:
                self._peer_last_heartbeat[peer_id] = time.monotonic()

    async def get_stale_peer_ids(self, timeout_seconds: float) -> list[str]:
        """Peers with no heartbeat response within timeout_seconds."""
        async with self._lock:
            now = time.monotonic()
            return [
                pid
                for pid, t in self._peer_last_heartbeat.items()
                if now - t > timeout_seconds
            ]

    async def get_peers_past_reconnect_grace(self, grace_seconds: float) -> list[str]:
        """Peers disconnected longer than grace_seconds."""
        async with self._lock:
            now = time.monotonic()
            return [
                pid
                for pid, t in self._peer_disconnected_at.items()
                if now - t > grace_seconds
            ]

    async def get_empty_rooms_past_ttl(self, ttl_seconds: float) -> list[str]:
        """Room IDs that are still empty after ttl_seconds since creation."""
        async with self._lock:
            now = time.monotonic()
            return [
                room_id
                for room_id, peers in self._room_to_peers.items()
                if not peers
                and now - self._room_created_at.get(room_id, now) > ttl_seconds
            ]

    # --- Snapshot ---

    async def snapshot(self) -> dict:
        """Full state snapshot for the dashboard."""
        async with self._lock:
            now = time.monotonic()
            rooms: dict[str, list[dict]] = {}
            for room_id, peer_ids in self._room_to_peers.items():
                peers = []
                for pid in peer_ids:
                    last_hb = self._peer_last_heartbeat.get(pid)
                    disc_at = self._peer_disconnected_at.get(pid)
                    peers.append(
                        {
                            "peer_id": pid,
                            "client_id": self._peer_to_client.get(pid, ""),
                            "connected": pid in self._connected_peers,
                            "last_heartbeat_ago": (
                                round(now - last_hb, 1) if last_hb is not None else None
                            ),
                            "disconnected_ago": (
                                round(now - disc_at, 1) if disc_at is not None else None
                            ),
                        }
                    )
                rooms[room_id] = peers
            return {
                "rooms": rooms,
                "stats": {
                    "total_rooms": len(self._room_to_peers),
                    "connected_peers": len(self._connected_peers),
                    "disconnected_peers": len(self._peer_disconnected_at),
                    "total_peers": len(self._peer_to_room),
                },
            }

    # --- Shutdown ---

    async def shutdown(self) -> None:
        """Clear all state."""
        async with self._lock:
            self._room_to_peers.clear()
            self._room_created_at.clear()
            self._room_to_client_peer.clear()
            self._peer_to_room.clear()
            self._peer_to_client.clear()
            self._connected_peers.clear()
            self._peer_last_heartbeat.clear()
            self._peer_disconnected_at.clear()
        logger.info("ConnectionStore shutdown complete")
