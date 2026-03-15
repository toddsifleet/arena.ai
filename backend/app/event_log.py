"""Event log: subscribes to ConnectionManager events, stores a circular buffer,
and fans out to connected dashboard WebSocket subscribers.

Flow on every state change
--------------------------
ConnectionManager._dispatch(RegistryEvent)
  → EventLog._on_registry_event(event)
      → translate event → EventPayload
      → append to circular buffer
      → send DashboardEvent  (type="EVENT")    to all dashboard WS subs
      → fetch fresh snapshot
      → send DashboardSnapshot (type="SNAPSHOT") to all dashboard WS subs

Signal events (offer/answer/candidate) are emitted directly via ``emit()``
and only fan out the EVENT message — they carry no state change.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from typing import TYPE_CHECKING, Any

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


def _translate(event: RegistryEvent) -> tuple[str, dict[str, Any]]:
    """Map a typed registry event to ``(event_type_string, data_dict)``."""
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
        self._subscribers: set[Any] = set()
        self._registry: ConnectionManager | None = None

    def subscribe_to_registry(self, registry: ConnectionManager) -> None:
        """Wire this log to a ConnectionManager so it receives all state-change events."""
        self._registry = registry
        registry.add_listener(self._on_registry_event)

    # --- Listeners ---

    async def _on_registry_event(self, event: RegistryEvent) -> None:
        """Translate, store, and broadcast; then push a fresh snapshot."""
        event_type, data = _translate(event)
        payload = self._record(event_type, data)
        await self._broadcast_event(payload)
        await self._broadcast_snapshot()

    async def emit(self, event_type: str, data: dict[str, Any]) -> EventPayload:
        """Emit a non-registry event (e.g. signaling messages).

        These are stored and broadcast as EVENT messages only — they carry
        no room-state change so no snapshot is pushed.
        """
        payload = self._record(event_type, data)
        await self._broadcast_event(payload)
        return payload

    # --- Internal helpers ---

    def _record(self, event_type: str, data: dict[str, Any]) -> EventPayload:
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
        if not self._registry or not self._subscribers:
            return
        raw = await self._registry.snapshot()
        msg = build_snapshot(raw)
        await self._fanout(msg)

    async def _fanout(self, msg: str) -> None:
        dead: set[Any] = set()
        for ws in list(self._subscribers):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.add(ws)
        self._subscribers -= dead

    # --- Dashboard WS subscription ---

    def subscribe(self, ws: Any) -> None:
        self._subscribers.add(ws)

    def unsubscribe(self, ws: Any) -> None:
        self._subscribers.discard(ws)

    def get_events(self) -> list[EventPayload]:
        return list(self._events)
