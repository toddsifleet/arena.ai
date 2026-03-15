"""WebSocket coordination layer for rooms and peers.

``ConnectionManager`` owns active WebSocket bindings and drives the heartbeat
loop.  All persistent room/peer state is delegated to the injected
``ConnectionStore``.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import BaseModel
from starlette.websockets import WebSocketDisconnect

from app.connection_store import ConnectionStore
from app.schemas import HeartbeatMessage, PresenceMessage, PresencePayload
from app.settings import settings
from app.value_objects import JoinResult, PeerInfo
from app.value_objects.registry_events import (
    PeerConnected,
    PeerDisconnected,
    PeerJoined,
    PeerRemoved,
    RegistryEvent,
    RoomCreated,
    RoomDestroyed,
)

logger = logging.getLogger(__name__)

Listener = Callable[[RegistryEvent], Awaitable[None]]


async def send_json(ws: Any, obj: BaseModel | dict[str, Any]) -> None:
    """Send a JSON message over a WebSocket, logging failures."""
    try:
        payload = obj.model_dump_json() if isinstance(obj, BaseModel) else json.dumps(obj)
        await ws.send_text(payload)
    except WebSocketDisconnect:
        logger.debug("send_json: client already disconnected")
    except Exception:
        logger.warning("send_json failed", exc_info=True)


class ConnectionManager:
    """Coordinates WebSocket connections using an injected ``ConnectionStore``.

    All persistent room/peer state lives in the store.  This class owns the
    active WebSocket bindings (``_peer_to_ws``, ``_room_presence_subs``),
    drives the heartbeat loop, broadcasts presence notifications, and
    dispatches typed ``RegistryEvent`` dataclasses to registered listeners.
    """

    def __init__(self, store: ConnectionStore) -> None:
        self._store = store
        self._peer_to_ws: dict[str, Any] = {}
        self._room_presence_subs: dict[str, set[Any]] = {}
        self._listeners: list[Listener] = []

    def add_listener(self, cb: Listener) -> None:
        self._listeners.append(cb)

    def remove_listener(self, cb: Listener) -> None:
        try:
            self._listeners.remove(cb)
        except ValueError:
            pass

    async def _dispatch(self, event: RegistryEvent) -> None:
        """Call every listener with the event. Errors are logged and swallowed."""
        for cb in list(self._listeners):
            try:
                await cb(event)
            except Exception:
                logger.exception("listener error for %s", type(event).__name__)

    async def create_room(self) -> str:
        room_id = await self._store.create_room()
        await self._dispatch(RoomCreated(room_id=room_id))
        return room_id

    async def room_exists(self, room_id: str) -> bool:
        return await self._store.room_exists(room_id)

    async def list_room_ids(self) -> list[str]:
        return await self._store.list_room_ids()

    async def join_room(self, room_id: str, client_id: str | None = None) -> JoinResult:
        result = await self._store.join_room(room_id, client_id)
        await self._dispatch(
            PeerJoined(
                room_id=result.room_id,
                peer_id=result.peer_id,
                client_id=result.client_id,
                reconnected=result.reconnected,
            )
        )
        return result

    async def list_peers(self, room_id: str) -> list[PeerInfo]:
        return await self._store.list_peers(room_id)

    async def register_peer_ws(self, peer_id: str, ws: Any) -> bool:
        """Bind a WebSocket to a peer. Returns True if the peer was reconnecting."""
        was_reconnecting = await self._store.mark_peer_connected(peer_id)
        self._peer_to_ws[peer_id] = ws
        room_id = await self._store.get_peer_room(peer_id) or ""
        await self._dispatch(
            PeerConnected(room_id=room_id, peer_id=peer_id, reconnected=was_reconnecting)
        )
        return was_reconnecting

    async def unregister_peer_ws(self, peer_id: str) -> str | None:
        """Detach WebSocket; keep peer in room for reconnect grace. Returns room_id."""
        self._peer_to_ws.pop(peer_id, None)
        room_id = await self._store.mark_peer_disconnected(peer_id)
        if room_id:
            await self._dispatch(PeerDisconnected(room_id=room_id, peer_id=peer_id))
        return room_id

    async def get_ws(self, peer_id: str) -> Any | None:
        return self._peer_to_ws.get(peer_id)

    async def get_all_peer_connections(self) -> list[tuple[str, Any]]:
        return list(self._peer_to_ws.items())


    async def peer_in_room(self, peer_id: str) -> str | None:
        return await self._store.get_peer_room(peer_id)

    async def get_other_peers_in_room(self, room_id: str, exclude_peer_id: str) -> list[str]:
        return await self._store.get_other_peers_in_room(room_id, exclude_peer_id)

    async def touch_heartbeat(self, peer_id: str) -> None:
        await self._store.touch_heartbeat(peer_id)

    async def remove_peer_from_room(self, peer_id: str, cause: str = "left") -> str | None:
        """Fully remove a peer from its room. Returns room_id if the peer was in one."""
        self._peer_to_ws.pop(peer_id, None)
        room_id, room_destroyed = await self._store.remove_peer(peer_id)
        if room_id:
            await self._dispatch(PeerRemoved(room_id=room_id, peer_id=peer_id, cause=cause))
        if room_destroyed:
            await self._dispatch(RoomDestroyed(room_id=room_id))
            await self._close_presence_subs_for_room(room_id)
        return room_id

    async def _close_presence_subs_for_room(self, room_id: str) -> None:
        """Close and discard all presence subscribers for a destroyed room."""
        subs = self._room_presence_subs.pop(room_id, None)
        if not subs:
            return
        for ws in subs:
            try:
                await ws.close()
            except Exception:
                logger.debug("failed to close presence sub for destroyed room %s", room_id)

    async def subscribe_presence(self, room_id: str, ws: Any) -> None:
        """Register ws as a presence subscriber and immediately flush the current snapshot."""
        self._room_presence_subs.setdefault(room_id, set()).add(ws)
        for peer in await self._store.list_peers(room_id):
            if peer.peer_id in self._peer_to_ws:
                await send_json(
                    ws,
                    PresenceMessage(
                        payload=PresencePayload(
                            kind="reconnected", peer_id=peer.peer_id, room_id=room_id
                        )
                    ),
                )

    async def add_presence_sub(self, room_id: str, ws: Any) -> None:
        self._room_presence_subs.setdefault(room_id, set()).add(ws)

    async def remove_presence_sub(self, room_id: str, ws: Any) -> None:
        subs = self._room_presence_subs.get(room_id)
        if subs:
            subs.discard(ws)
            if not subs:
                del self._room_presence_subs[room_id]

    async def get_presence_subs(self, room_id: str) -> list[Any]:
        return list(self._room_presence_subs.get(room_id, set()))

    async def snapshot(self) -> dict:
        return await self._store.snapshot()


    async def notify_presence(
        self,
        peer_id: str,
        room_id: str,
        kind: Literal["joined", "reconnected", "disconnected", "left"],
    ) -> None:
        """Broadcast a presence event to every other peer and all presence subscribers."""
        msg = PresenceMessage(
            payload=PresencePayload(kind=kind, peer_id=peer_id, room_id=room_id)
        )
        for other_id in await self._store.get_other_peers_in_room(room_id, peer_id):
            ws = self._peer_to_ws.get(other_id)
            if ws:
                await send_json(ws, msg)
        for sub_ws in self._room_presence_subs.get(room_id, set()):
            await send_json(sub_ws, msg)

    async def _evict_stale_peers(self) -> None:
        for peer_id, ws in list(self._peer_to_ws.items()):
            try:
                await send_json(ws, HeartbeatMessage())
            except Exception:
                logger.debug("heartbeat send failed for %s", peer_id)

        for peer_id in await self._store.get_stale_peer_ids(settings.heartbeat_timeout_seconds):
            ws = self._peer_to_ws.get(peer_id)
            if ws:
                try:
                    await ws.close()
                except Exception:
                    logger.debug("failed to close ws for stale peer %s", peer_id)
            room_id = await self.remove_peer_from_room(peer_id, cause="evicted_stale")
            if room_id:
                await self.notify_presence(peer_id, room_id, "disconnected")
                logger.info("Evicted stale peer %s from room %s", peer_id, room_id)

        for peer_id in await self._store.get_peers_past_reconnect_grace(
            settings.reconnect_grace_seconds
        ):
            room_id = await self.remove_peer_from_room(peer_id, cause="evicted")
            if room_id:
                await self.notify_presence(peer_id, room_id, "left")
                logger.info(
                    "Removed peer %s past reconnect grace from room %s", peer_id, room_id
                )

        for room_id in await self._store.get_empty_rooms_past_ttl(settings.empty_room_ttl_seconds):
            removed = await self._store.remove_room_if_empty(room_id)
            if removed:
                await self._dispatch(RoomDestroyed(room_id=room_id))
                await self._close_presence_subs_for_room(room_id)
                logger.info("Removed empty room %s past TTL", room_id)

    async def heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(settings.heartbeat_interval_seconds)
            try:
                await self._evict_stale_peers()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("heartbeat_loop error")

    async def close_all_peer_connections(self) -> None:
        for peer_id, ws in list(self._peer_to_ws.items()):
            try:
                await ws.close()
            except Exception:
                logger.debug("shutdown close failed for %s", peer_id)
        self._peer_to_ws.clear()
        logger.info("Closed all peer connections")

    async def shutdown(self) -> None:
        self._peer_to_ws.clear()
        self._room_presence_subs.clear()
        self._listeners.clear()
        await self._store.shutdown()
