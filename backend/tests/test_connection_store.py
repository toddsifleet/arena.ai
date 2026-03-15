"""Tests for ConnectionStore — the pure in-memory state store."""
import time

import pytest

from app.connection_store import ConnectionStore


@pytest.fixture
def store():
    return ConnectionStore()


@pytest.mark.asyncio
async def test_empty_room_ttl_candidates(store):
    room_id = await store.create_room()
    async with store._lock:
        store._room_created_at[room_id] = time.monotonic() - 1000
    stale = await store.get_empty_rooms_past_ttl(300.0)
    assert room_id in stale


@pytest.mark.asyncio
async def test_remove_room_if_empty(store):
    room_id = await store.create_room()
    removed = await store.remove_room_if_empty(room_id)
    assert removed is True
    assert not await store.room_exists(room_id)


@pytest.mark.asyncio
async def test_remove_room_if_empty_noop_when_not_empty(store):
    room_id = await store.create_room()
    await store.join_room(room_id)
    removed = await store.remove_room_if_empty(room_id)
    assert removed is False
    assert await store.room_exists(room_id)


@pytest.mark.asyncio
async def test_get_stale_peer_ids(store):
    room_id = await store.create_room()
    result = await store.join_room(room_id)
    await store.mark_peer_connected(result.peer_id)

    async with store._lock:
        store._peer_last_heartbeat[result.peer_id] = time.monotonic() - 20

    stale = await store.get_stale_peer_ids(10.0)
    assert result.peer_id in stale


@pytest.mark.asyncio
async def test_get_peers_past_reconnect_grace(store):
    room_id = await store.create_room()
    result = await store.join_room(room_id)
    await store.mark_peer_connected(result.peer_id)
    await store.mark_peer_disconnected(result.peer_id)

    async with store._lock:
        store._peer_disconnected_at[result.peer_id] = time.monotonic() - 20

    past = await store.get_peers_past_reconnect_grace(10.0)
    assert result.peer_id in past
