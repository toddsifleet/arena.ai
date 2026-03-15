"""Tests for room REST endpoints."""


def test_create_room(client):
    resp = client.post("/rooms")
    assert resp.status_code == 200
    data = resp.json()
    assert "room_id" in data
    assert len(data["room_id"]) >= 12


def test_create_room_emits_event(client, test_event_log):
    client.post("/rooms")
    types = [e.type for e in test_event_log.get_events()]
    assert "room.created" in types


def test_join_room(client):
    room_id = client.post("/rooms").json()["room_id"]
    resp = client.get(f"/rooms/{room_id}/join")
    assert resp.status_code == 200
    data = resp.json()
    assert data["room_id"] == room_id
    assert "peer_id" in data
    assert "client_id" in data
    assert data["signaling_path"] == "/peerjs"


def test_join_room_emits_event(client, test_event_log):
    room_id = client.post("/rooms").json()["room_id"]
    client.get(f"/rooms/{room_id}/join")
    types = [e.type for e in test_event_log.get_events()]
    assert "peer.joined" in types


def test_join_room_not_found(client):
    resp = client.get("/rooms/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/join")
    assert resp.status_code == 404


def test_join_room_invalid_id(client):
    """A non-UUID room_id path parameter is rejected with a 4xx error."""
    resp = client.get("/rooms/short/join")
    # FastAPI returns 422 for path parameter validation failures
    assert resp.status_code == 422


def test_join_room_full(client):
    room_id = client.post("/rooms").json()["room_id"]
    client.get(f"/rooms/{room_id}/join")
    client.get(f"/rooms/{room_id}/join")
    resp = client.get(f"/rooms/{room_id}/join")
    assert resp.status_code == 403


def test_join_room_already_connected(client):
    """Attempting to reconnect while the WS is still active returns 409."""
    room_id = client.post("/rooms").json()["room_id"]
    peer = client.get(f"/rooms/{room_id}/join").json()
    with client.websocket_connect(f"/peerjs?id={peer['peer_id']}") as ws:
        ws.receive_json()  # OPEN — WS now active/registered
        resp = client.get(f"/rooms/{room_id}/join?client_id={peer['client_id']}")
        assert resp.status_code == 409


def test_join_room_reconnect_slot(client):
    room_id = client.post("/rooms").json()["room_id"]
    first = client.get(f"/rooms/{room_id}/join").json()
    cid = first["client_id"]
    second = client.get(f"/rooms/{room_id}/join?client_id={cid}").json()
    assert second["peer_id"] == first["peer_id"]
    assert second["client_id"] == first["client_id"]


def test_join_room_reconnect_emits_event(client, test_event_log):
    room_id = client.post("/rooms").json()["room_id"]
    first = client.get(f"/rooms/{room_id}/join").json()
    client.get(f"/rooms/{room_id}/join?client_id={first['client_id']}")
    types = [e.type for e in test_event_log.get_events()]
    assert "peer.reconnected" in types


def test_list_peers_empty(client):
    room_id = client.post("/rooms").json()["room_id"]
    resp = client.get(f"/rooms/{room_id}/peers")
    assert resp.status_code == 200
    assert resp.json()["peers"] == []


def test_list_peers_after_join(client):
    room_id = client.post("/rooms").json()["room_id"]
    joined = client.get(f"/rooms/{room_id}/join").json()
    resp = client.get(f"/rooms/{room_id}/peers")
    peers = resp.json()["peers"]
    assert len(peers) == 1
    assert peers[0]["id"] == joined["peer_id"]
    assert peers[0]["connected"] is False  # no WS connection yet


def test_list_peers_connected_status(client):
    """connected flag reflects whether the peer has an active signaling WS."""
    room_id = client.post("/rooms").json()["room_id"]
    peer = client.get(f"/rooms/{room_id}/join").json()
    with client.websocket_connect(f"/peerjs?id={peer['peer_id']}") as ws:
        ws.receive_json()  # OPEN
        peers = client.get(f"/rooms/{room_id}/peers").json()["peers"]
        assert peers[0]["connected"] is True
    # After disconnect, connected should revert
    peers = client.get(f"/rooms/{room_id}/peers").json()["peers"]
    assert peers[0]["connected"] is False
