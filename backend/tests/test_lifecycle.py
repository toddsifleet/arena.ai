"""Tests for heartbeat, eviction, and shutdown."""
import asyncio
import time

import pytest

from app.connection_manager import ConnectionManager
from app.connection_store import ConnectionStore
from app.event_log import EventLog


class FakeWS:
    """Minimal WebSocket stub that records sends and tracks close calls."""

    def __init__(self):
        self.sent: list[str] = []
        self.closed = False

    async def send_text(self, data: str) -> None:
        self.sent.append(data)

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def reg():
    return ConnectionManager(store=ConnectionStore())


@pytest.fixture
def el(reg):
    el = EventLog()
    el.subscribe_to_connection_manager(reg)
    return el


@pytest.mark.asyncio
async def test_heartbeat_loop_cancellable():
    """heartbeat_loop shuts down cleanly when its task is cancelled."""
    reg = ConnectionManager(store=ConnectionStore())
    task = asyncio.create_task(reg.heartbeat_loop())
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_evict_noop_when_empty():
    """With no peers registered, eviction completes without error and leaves state clean."""
    reg = ConnectionManager(store=ConnectionStore())
    await reg._evict_stale_peers()
    assert await reg.list_room_ids() == []
    snap = await reg.snapshot()
    assert snap["stats"]["total_peers"] == 0


@pytest.mark.asyncio
async def test_evict_stale_peer(reg, el):
    """A peer whose heartbeat timed out is evicted and removed from the room."""
    room_id = await reg.create_room()
    result = await reg.join_room(room_id)
    ws = FakeWS()
    await reg.register_peer_ws(result.peer_id, ws)

    # Backdate heartbeat far beyond the timeout threshold
    async with reg._store._lock:
        reg._store._peer_last_heartbeat[result.peer_id] = time.monotonic() - 100

    await reg._evict_stale_peers()

    assert await reg.peer_in_room(result.peer_id) is None
    assert ws.closed

    event_types = [e.type for e in el.get_events()]
    assert "peer.evicted_stale" in event_types


@pytest.mark.asyncio
async def test_evict_stale_peer_emits_disconnected_presence(reg, el):
    """Evicting a stale peer notifies the other peer with a 'disconnected' presence."""
    room_id = await reg.create_room()
    peer_a = await reg.join_room(room_id)
    peer_b = await reg.join_room(room_id)

    ws_a = FakeWS()
    ws_b = FakeWS()
    await reg.register_peer_ws(peer_a.peer_id, ws_a)
    await reg.register_peer_ws(peer_b.peer_id, ws_b)

    # Only peer_a goes stale
    async with reg._store._lock:
        reg._store._peer_last_heartbeat[peer_a.peer_id] = time.monotonic() - 100

    await reg._evict_stale_peers()

    import json
    presence_msgs = [
        json.loads(m)
        for m in ws_b.sent
        if json.loads(m).get("type") == "PRESENCE"
    ]
    assert any(m["payload"]["kind"] == "disconnected" for m in presence_msgs)


@pytest.mark.asyncio
async def test_evict_peer_past_reconnect_grace(reg, el):
    """A peer past reconnect grace is fully removed from the room."""
    room_id = await reg.create_room()
    result = await reg.join_room(room_id)
    await reg.register_peer_ws(result.peer_id, FakeWS())
    await reg.unregister_peer_ws(result.peer_id)

    # Backdate disconnect time far beyond grace period
    async with reg._store._lock:
        reg._store._peer_disconnected_at[result.peer_id] = time.monotonic() - 100

    await reg._evict_stale_peers()

    assert await reg.peer_in_room(result.peer_id) is None

    event_types = [e.type for e in el.get_events()]
    assert "peer.evicted" in event_types


@pytest.mark.asyncio
async def test_evict_emits_room_destroyed_when_last_peer(reg, el):
    """room.destroyed is emitted when evicting the last peer destroys the room."""
    room_id = await reg.create_room()
    result = await reg.join_room(room_id)
    await reg.register_peer_ws(result.peer_id, FakeWS())

    async with reg._store._lock:
        reg._store._peer_last_heartbeat[result.peer_id] = time.monotonic() - 100

    await reg._evict_stale_peers()

    event_types = [e.type for e in el.get_events()]
    assert "room.destroyed" in event_types


@pytest.mark.asyncio
async def test_evict_grace_emits_room_destroyed(reg, el):
    """room.destroyed is emitted when grace-period eviction empties the room."""
    room_id = await reg.create_room()
    result = await reg.join_room(room_id)
    await reg.register_peer_ws(result.peer_id, FakeWS())
    await reg.unregister_peer_ws(result.peer_id)

    async with reg._store._lock:
        reg._store._peer_disconnected_at[result.peer_id] = time.monotonic() - 100

    await reg._evict_stale_peers()

    event_types = [e.type for e in el.get_events()]
    assert "room.destroyed" in event_types


@pytest.mark.asyncio
async def test_close_all_peer_connections():
    """close_all_peer_connections closes every active WebSocket."""
    reg = ConnectionManager(store=ConnectionStore())
    room_id = await reg.create_room()
    a = await reg.join_room(room_id)
    b = await reg.join_room(room_id)

    ws_a, ws_b = FakeWS(), FakeWS()
    await reg.register_peer_ws(a.peer_id, ws_a)
    await reg.register_peer_ws(b.peer_id, ws_b)

    await reg.close_all_peer_connections()

    assert ws_a.closed
    assert ws_b.closed


@pytest.mark.asyncio
async def test_close_all_tolerates_failing_ws():
    """close_all_peer_connections continues even if a WebSocket raises on close."""

    class BrokenWS:
        async def close(self):
            raise RuntimeError("already closed")

    reg = ConnectionManager(store=ConnectionStore())
    room_id = await reg.create_room()
    result = await reg.join_room(room_id)
    await reg.register_peer_ws(result.peer_id, BrokenWS())

    await reg.close_all_peer_connections()

    # Exception was swallowed and cleanup still completed
    assert await reg.get_ws(result.peer_id) is None
    assert await reg.get_all_peer_connections() == []
