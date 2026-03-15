"""Tests for dashboard REST snapshot and WebSocket stream endpoints."""
import pytest


# ---------------------------------------------------------------------------
# GET /dashboard/snapshot
# ---------------------------------------------------------------------------


def test_snapshot_empty(client):
    resp = client.get("/dashboard/snapshot")
    assert resp.status_code == 200
    data = resp.json()
    assert "rooms" in data
    assert "stats" in data
    assert "events" in data
    assert data["stats"]["total_rooms"] == 0
    assert data["stats"]["connected_peers"] == 0


def test_snapshot_after_room_created(client):
    client.post("/rooms")
    data = client.get("/dashboard/snapshot").json()
    assert data["stats"]["total_rooms"] == 1


def test_snapshot_after_peer_joined(client):
    room_id = client.post("/rooms").json()["room_id"]
    client.get(f"/rooms/{room_id}/join")

    data = client.get("/dashboard/snapshot").json()
    assert data["stats"]["total_rooms"] == 1
    assert data["stats"]["total_peers"] == 1
    assert data["stats"]["connected_peers"] == 0
    assert room_id in data["rooms"]


def test_snapshot_connected_peer(client):
    room_id = client.post("/rooms").json()["room_id"]
    peer = client.get(f"/rooms/{room_id}/join").json()

    with client.websocket_connect(f"/peerjs?id={peer['peer_id']}") as ws:
        ws.receive_json()  # OPEN
        data = client.get("/dashboard/snapshot").json()
        assert data["stats"]["connected_peers"] == 1

    # After disconnect
    data = client.get("/dashboard/snapshot").json()
    assert data["stats"]["connected_peers"] == 0
    assert data["stats"]["disconnected_peers"] == 1


def test_snapshot_includes_events(client, test_event_log):
    room_id = client.post("/rooms").json()["room_id"]
    client.get(f"/rooms/{room_id}/join")

    data = client.get("/dashboard/snapshot").json()
    # Events are returned as dicts; check that expected types appear
    event_types = [e["type"] for e in data["events"]]
    assert "room.created" in event_types
    assert "peer.joined" in event_types


def test_snapshot_room_peer_detail(client):
    room_id = client.post("/rooms").json()["room_id"]
    joined = client.get(f"/rooms/{room_id}/join").json()

    data = client.get("/dashboard/snapshot").json()
    room_peers = data["rooms"][room_id]
    assert len(room_peers) == 1
    assert room_peers[0]["peer_id"] == joined["peer_id"]
    assert room_peers[0]["connected"] is False


# ---------------------------------------------------------------------------
# WS /dashboard/stream
# ---------------------------------------------------------------------------


def test_stream_sends_initial_snapshot(client):
    """On connect the stream immediately sends a SNAPSHOT message."""
    with client.websocket_connect("/dashboard/stream") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "SNAPSHOT"
        assert "rooms" in msg
        assert "stats" in msg


def test_stream_initial_snapshot_includes_events(client, test_event_log):
    room_id = client.post("/rooms").json()["room_id"]

    with client.websocket_connect("/dashboard/stream") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "SNAPSHOT"
        event_types = [e["type"] for e in msg.get("events", [])]
        assert "room.created" in event_types


def test_stream_receives_event_push(client, test_registry):
    """After connecting, new events are pushed as EVENT messages."""
    with client.websocket_connect("/dashboard/stream") as ws:
        ws.receive_json()  # initial SNAPSHOT

        # Call reg.create_room() directly via the TestClient's anyio portal so it
        # runs on the same event loop as the WebSocket handler.  A plain HTTP POST
        # would deadlock because TestClient is single-threaded and the server would
        # try to push to the open WS while the test thread is blocked waiting for
        # the HTTP response.
        client.portal.call(test_registry.create_room)

        msg = ws.receive_json()
        assert msg["type"] == "EVENT"
        assert msg["event"]["type"] == "room.created"
