"""Tests for ConnectionManager — room/peer lifecycle, WebSocket registration, eviction."""
import asyncio
import json
import time

import pytest

from app.connection_manager import ConnectionManager
from app.connection_store import ConnectionStore
from app.event_log import EventLog
from app.value_objects import AlreadyConnected, RoomFull, RoomNotFound


class FakeWS:
    """Minimal WebSocket stub that records sends and tracks close calls."""

    def __init__(self):
        self.sent = []
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


# ---------------------------------------------------------------------------
# Room creation / listing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_room(reg):
    room_id = await reg.create_room()
    assert await reg.room_exists(room_id)
    assert not await reg.room_exists("nonexistent")


@pytest.mark.asyncio
async def test_list_room_ids_empty(reg):
    assert await reg.list_room_ids() == []


@pytest.mark.asyncio
async def test_list_room_ids(reg):
    r1 = await reg.create_room()
    r2 = await reg.create_room()
    ids = await reg.list_room_ids()
    assert set(ids) == {r1, r2}


# ---------------------------------------------------------------------------
# Joining rooms
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_join_room(reg):
    room_id = await reg.create_room()
    result = await reg.join_room(room_id)
    assert result.room_id == room_id
    assert result.peer_id
    assert result.client_id
    assert not result.reconnected


@pytest.mark.asyncio
async def test_join_room_not_found(reg):
    with pytest.raises(RoomNotFound):
        await reg.join_room("nonexistent-room-id-long-enough")


@pytest.mark.asyncio
async def test_join_room_full(reg):
    room_id = await reg.create_room()
    await reg.join_room(room_id)
    await reg.join_room(room_id)
    with pytest.raises(RoomFull):
        await reg.join_room(room_id)


@pytest.mark.asyncio
async def test_join_room_reconnect_slot(reg):
    room_id = await reg.create_room()
    first = await reg.join_room(room_id)
    second = await reg.join_room(room_id, client_id=first.client_id)
    assert second.peer_id == first.peer_id
    assert second.reconnected


@pytest.mark.asyncio
async def test_join_room_already_connected(reg):
    room_id = await reg.create_room()
    result = await reg.join_room(room_id)
    await reg.register_peer_ws(result.peer_id, object())
    with pytest.raises(AlreadyConnected):
        await reg.join_room(room_id, client_id=result.client_id)


# ---------------------------------------------------------------------------
# WebSocket registration / unregistration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_unregister_ws(reg):
    room_id = await reg.create_room()
    result = await reg.join_room(room_id)

    was_reconnecting = await reg.register_peer_ws(result.peer_id, object())
    assert not was_reconnecting
    assert await reg.get_ws(result.peer_id) is not None

    await reg.unregister_peer_ws(result.peer_id)
    assert await reg.get_ws(result.peer_id) is None


@pytest.mark.asyncio
async def test_reconnect_detection(reg):
    room_id = await reg.create_room()
    result = await reg.join_room(room_id)

    await reg.register_peer_ws(result.peer_id, object())
    await reg.unregister_peer_ws(result.peer_id)

    was_reconnecting = await reg.register_peer_ws(result.peer_id, object())
    assert was_reconnecting


@pytest.mark.asyncio
async def test_unregister_sets_disconnected_at(reg):
    """unregister_peer_ws records the disconnect timestamp so grace eviction works."""
    room_id = await reg.create_room()
    result = await reg.join_room(room_id)
    await reg.register_peer_ws(result.peer_id, object())
    before = time.monotonic()
    await reg.unregister_peer_ws(result.peer_id)

    async with reg._store._lock:
        disc = reg._store._peer_disconnected_at.get(result.peer_id)
    assert disc is not None
    assert disc >= before


# ---------------------------------------------------------------------------
# Peer / room lookup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_peer_in_room(reg):
    room_id = await reg.create_room()
    result = await reg.join_room(room_id)
    assert await reg.peer_in_room(result.peer_id) == room_id
    assert await reg.peer_in_room("nonexistent") is None


@pytest.mark.asyncio
async def test_get_other_peers_in_room(reg):
    room_id = await reg.create_room()
    a = await reg.join_room(room_id)
    b = await reg.join_room(room_id)

    assert await reg.get_other_peers_in_room(room_id, a.peer_id) == [b.peer_id]
    assert await reg.get_other_peers_in_room(room_id, b.peer_id) == [a.peer_id]


@pytest.mark.asyncio
async def test_get_other_peers_unknown_room(reg):
    assert await reg.get_other_peers_in_room("no-room", "no-peer") == []


# ---------------------------------------------------------------------------
# Removing peers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_peer_from_room(reg):
    room_id = await reg.create_room()
    a = await reg.join_room(room_id)
    b = await reg.join_room(room_id)

    removed_room = await reg.remove_peer_from_room(a.peer_id)
    assert removed_room == room_id
    assert await reg.peer_in_room(a.peer_id) is None
    assert await reg.get_other_peers_in_room(room_id, b.peer_id) == []


@pytest.mark.asyncio
async def test_remove_peer_destroys_room_when_last(reg):
    room_id = await reg.create_room()
    result = await reg.join_room(room_id)

    removed_room = await reg.remove_peer_from_room(result.peer_id)
    assert removed_room == room_id
    assert not await reg.room_exists(room_id)


@pytest.mark.asyncio
async def test_remove_unknown_peer_noop(reg):
    removed_room = await reg.remove_peer_from_room("nonexistent-peer")
    assert removed_room is None


# ---------------------------------------------------------------------------
# Listing peers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_peers(reg):
    room_id = await reg.create_room()
    a = await reg.join_room(room_id)
    await reg.register_peer_ws(a.peer_id, object())
    b = await reg.join_room(room_id)

    peers = await reg.list_peers(room_id)
    assert len(peers) == 2

    by_id = {p.peer_id: p for p in peers}
    assert by_id[a.peer_id].connected is True
    assert by_id[b.peer_id].connected is False


@pytest.mark.asyncio
async def test_list_peers_unknown_room(reg):
    assert await reg.list_peers("nonexistent") == []


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_touch_heartbeat(reg):
    room_id = await reg.create_room()
    result = await reg.join_room(room_id)
    await reg.register_peer_ws(result.peer_id, object())

    async with reg._store._lock:
        reg._store._peer_last_heartbeat[result.peer_id] = time.monotonic() - 100

    await reg.touch_heartbeat(result.peer_id)

    stale = await reg._store.get_stale_peer_ids(10.0)
    assert result.peer_id not in stale


@pytest.mark.asyncio
async def test_touch_heartbeat_unknown_peer_noop(reg):
    """touch_heartbeat for an unknown peer should not raise or create a heartbeat entry."""
    await reg.touch_heartbeat("nonexistent-peer")
    assert reg._store._peer_last_heartbeat.get("nonexistent-peer") is None


# ---------------------------------------------------------------------------
# All peer connections
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_all_peer_connections(reg):
    room_id = await reg.create_room()
    a = await reg.join_room(room_id)
    b = await reg.join_room(room_id)
    ws_a, ws_b = object(), object()
    await reg.register_peer_ws(a.peer_id, ws_a)
    await reg.register_peer_ws(b.peer_id, ws_b)

    conns = await reg.get_all_peer_connections()
    assert len(conns) == 2
    assert dict(conns) == {a.peer_id: ws_a, b.peer_id: ws_b}


# ---------------------------------------------------------------------------
# Presence subscriptions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_presence_subs_add_get_remove(reg):
    room_id = await reg.create_room()
    ws1, ws2 = object(), object()

    await reg.add_presence_sub(room_id, ws1)
    await reg.add_presence_sub(room_id, ws2)
    subs = await reg.get_presence_subs(room_id)
    assert set(subs) == {ws1, ws2}

    await reg.remove_presence_sub(room_id, ws1)
    subs = await reg.get_presence_subs(room_id)
    assert subs == [ws2]

    await reg.remove_presence_sub(room_id, ws2)
    assert await reg.get_presence_subs(room_id) == []


@pytest.mark.asyncio
async def test_presence_subs_unknown_room(reg):
    assert await reg.get_presence_subs("no-room") == []


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_snapshot_empty(reg):
    snap = await reg.snapshot()
    assert snap["rooms"] == {}
    assert snap["stats"]["total_rooms"] == 0
    assert snap["stats"]["connected_peers"] == 0
    assert snap["stats"]["total_peers"] == 0


@pytest.mark.asyncio
async def test_snapshot_with_connected_peer(reg):
    room_id = await reg.create_room()
    result = await reg.join_room(room_id)
    await reg.register_peer_ws(result.peer_id, object())

    snap = await reg.snapshot()
    assert snap["stats"]["total_rooms"] == 1
    assert snap["stats"]["total_peers"] == 1
    assert snap["stats"]["connected_peers"] == 1
    assert snap["stats"]["disconnected_peers"] == 0
    assert room_id in snap["rooms"]

    peer_data = snap["rooms"][room_id][0]
    assert peer_data["peer_id"] == result.peer_id
    assert peer_data["connected"] is True
    assert peer_data["last_heartbeat_ago"] is not None


@pytest.mark.asyncio
async def test_snapshot_with_disconnected_peer(reg):
    room_id = await reg.create_room()
    result = await reg.join_room(room_id)
    await reg.register_peer_ws(result.peer_id, object())
    await reg.unregister_peer_ws(result.peer_id)

    snap = await reg.snapshot()
    assert snap["stats"]["connected_peers"] == 0
    assert snap["stats"]["disconnected_peers"] == 1

    peer_data = snap["rooms"][room_id][0]
    assert peer_data["connected"] is False
    assert peer_data["disconnected_ago"] is not None


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shutdown(reg):
    room_id = await reg.create_room()
    result = await reg.join_room(room_id)
    await reg.register_peer_ws(result.peer_id, object())

    await reg.shutdown()

    assert not await reg.room_exists(room_id)
    snap = await reg.snapshot()
    assert snap["stats"]["total_rooms"] == 0
    assert snap["stats"]["total_peers"] == 0


# ---------------------------------------------------------------------------
# Heartbeat loop & eviction
# ---------------------------------------------------------------------------


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

    async with reg._store._lock:
        reg._store._peer_last_heartbeat[peer_a.peer_id] = time.monotonic() - 100

    await reg._evict_stale_peers()

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


# ---------------------------------------------------------------------------
# Close all connections
# ---------------------------------------------------------------------------


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

    assert await reg.get_ws(result.peer_id) is None
    assert await reg.get_all_peer_connections() == []
