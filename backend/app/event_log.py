"""Circular event buffer that subscribes to ConnectionManager events and fans out
to dashboard WebSocket subscribers."""
from __future__ import annotations

import logging
import time
from collections import deque
from typing import TYPE_CHECKING

from app.protocols import SubscriberLike
from app.schemas import DashboardEvent, EventPayload, build_snapshot
from app.value_objects.registry_events import (
    PeerConnected,
    PeerDisconnected,
    PeerJoined,
    PeerRemoved,
    RegistryEvent,
    RoomCreated,
    RoomDestroyed,
)

if TYPE_CHECKING:
    from app.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)


def _translate(event: RegistryEvent) -> tuple[str, dict[str, str | bool]]:
    if isinstance(event, RoomCreated):
        return "room.created", {"room_id": event.room_id}

    if isinstance(event, RoomDestroyed):
        return "room.destroyed", {"room_id": event.room_id}

    if isinstance(event, PeerJoined):
        kind = "peer.reconnected" if event.reconnected else "peer.joined"
        return kind, {
            "room_id": event.room_id,
            "peer_id": event.peer_id,
            "client_id": event.client_id,
        }

    if isinstance(event, PeerConnected):
        return "ws.connected", {
            "room_id": event.room_id,
            "peer_id": event.peer_id,
            "reconnected": event.reconnected,
        }

    if isinstance(event, PeerDisconnected):
        return "ws.disconnected", {"room_id": event.room_id, "peer_id": event.peer_id}

    if isinstance(event, PeerRemoved):
        event_type = {
            "left": "peer.left",
            "evicted_stale": "peer.evicted_stale",
            "evicted": "peer.evicted",
        }.get(event.cause, "peer.removed")
        return event_type, {"room_id": event.room_id, "peer_id": event.peer_id, "cause": event.cause}

    # Fallback for any future event types
    return type(event).__name__.lower(), {}


class EventLog:
    def __init__(self, maxlen: int = 200) -> None:
        self._events: deque[EventPayload] = deque(maxlen=maxlen)
        self._counter: int = 0
        self._subscribers: set[SubscriberLike] = set()
        self._connection_manager: ConnectionManager | None = None

    def subscribe_to_connection_manager(self, connection_manager: ConnectionManager) -> None:
        self._connection_manager = connection_manager
        connection_manager.add_listener(self._on_connection_manager_event)

    async def _on_connection_manager_event(self, event: RegistryEvent) -> None:
        event_type, data = _translate(event)
        payload = self._record(event_type, data)
        await self._broadcast_event(payload)
        await self._broadcast_snapshot()

    async def emit(self, event_type: str, data: dict[str, str | bool]) -> EventPayload:
        """Emit a non-connection-manager event (e.g. signaling messages).

        These are stored and broadcast as EVENT messages only — they carry
        no room-state change so no snapshot is pushed.
        """
        payload = self._record(event_type, data)
        await self._broadcast_event(payload)
        return payload

    def _record(self, event_type: str, data: dict[str, str | bool]) -> EventPayload:
        self._counter += 1
        payload = EventPayload(
            id=self._counter,
            type=event_type,
            data=data,
            timestamp=time.time(),
        )
        self._events.append(payload)
        return payload

    async def _broadcast_event(self, payload: EventPayload) -> None:
        msg = DashboardEvent(event=payload).model_dump_json()
        await self._fanout(msg)

    async def _broadcast_snapshot(self) -> None:
        if not self._connection_manager or not self._subscribers:
            return
        raw = await self._connection_manager.snapshot()
        msg = build_snapshot(raw)
        await self._fanout(msg)

    async def _fanout(self, msg: str) -> None:
        dead: set[SubscriberLike] = set()
        for ws in list(self._subscribers):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.add(ws)
        self._subscribers -= dead

    def subscribe(self, ws: SubscriberLike) -> None:
        self._subscribers.add(ws)

    def unsubscribe(self, ws: SubscriberLike) -> None:
        self._subscribers.discard(ws)

    def get_events(self) -> list[EventPayload]:
        return list(self._events)
