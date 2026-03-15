"""Tests for the room presence WebSocket endpoint (/rooms/{room_id}/presence)."""
import pytest


def test_presence_ws_connects(client):
    """A presence subscriber can connect and stays open without error."""
    room_id = client.post("/rooms").json()["room_id"]
    with client.websocket_connect(f"/rooms/{room_id}/presence"):
        pass  # Clean connect + disconnect is enough


def test_presence_ws_rejects_invalid_uuid_room_id(client):
    with pytest.raises(Exception):
        with client.websocket_connect("/rooms/not-a-uuid/presence"):
            pass


def test_presence_ws_receives_peer_joined(client):
    """Presence subscriber receives PRESENCE(joined) when a peer connects via signaling."""
    room_id = client.post("/rooms").json()["room_id"]
    peer_a = client.get(f"/rooms/{room_id}/join").json()
    peer_b = client.get(f"/rooms/{room_id}/join").json()

    with client.websocket_connect(f"/rooms/{room_id}/presence") as pres_ws:
        with client.websocket_connect(f"/peerjs?id={peer_a['peer_id']}") as ws_a:
            ws_a.receive_json()  # OPEN for peer_a
            pres_ws.receive_json()  # PRESENCE(joined, peer_a) - consume

            with client.websocket_connect(f"/peerjs?id={peer_b['peer_id']}") as ws_b:
                ws_b.receive_json()  # OPEN for peer_b
                ws_a.receive_json()  # PRESENCE on signaling WS

                msg = pres_ws.receive_json()
                assert msg["type"] == "PRESENCE"
                assert msg["payload"]["kind"] == "joined"
                assert msg["payload"]["peer_id"] == peer_b["peer_id"]
                assert msg["payload"]["room_id"] == room_id


def test_presence_ws_receives_peer_disconnected(client):
    """Presence subscriber sees PRESENCE(disconnected) when a peer's WS closes."""
    room_id = client.post("/rooms").json()["room_id"]
    peer = client.get(f"/rooms/{room_id}/join").json()

    with client.websocket_connect(f"/rooms/{room_id}/presence") as pres_ws:
        with client.websocket_connect(f"/peerjs?id={peer['peer_id']}") as ws:
            ws.receive_json()  # OPEN
            pres_ws.receive_json()  # PRESENCE(joined)

        # WS closed without LEAVE → disconnected
        msg = pres_ws.receive_json()
        assert msg["type"] == "PRESENCE"
        assert msg["payload"]["kind"] == "disconnected"
        assert msg["payload"]["peer_id"] == peer["peer_id"]


def test_presence_ws_receives_peer_left(client):
    """Presence subscriber sees PRESENCE(left) when a peer sends an explicit LEAVE."""
    room_id = client.post("/rooms").json()["room_id"]
    peer = client.get(f"/rooms/{room_id}/join").json()

    with client.websocket_connect(f"/rooms/{room_id}/presence") as pres_ws:
        with client.websocket_connect(f"/peerjs?id={peer['peer_id']}") as ws:
            ws.receive_json()  # OPEN
            pres_ws.receive_json()  # PRESENCE(joined)
            ws.send_json({"type": "LEAVE"})

        msg = pres_ws.receive_json()
        assert msg["type"] == "PRESENCE"
        assert msg["payload"]["kind"] == "left"


def test_presence_ws_subscriber_removed_on_disconnect(client):
    """After the presence WS closes, the registry removes it from subscribers."""
    room_id = client.post("/rooms").json()["room_id"]
    peer = client.get(f"/rooms/{room_id}/join").json()

    with client.websocket_connect(f"/rooms/{room_id}/presence"):
        pass  # connect and immediately disconnect

    # Connect peer via signaling; if the dead subscriber were still registered
    # it would cause a send error — the test just verifies no crash occurs.
    with client.websocket_connect(f"/peerjs?id={peer['peer_id']}") as ws:
        assert ws.receive_json()["type"] == "OPEN"


def test_multiple_presence_subscribers(client):
    """Both presence subscribers receive events when a peer joins."""
    room_id = client.post("/rooms").json()["room_id"]
    peer = client.get(f"/rooms/{room_id}/join").json()

    with client.websocket_connect(f"/rooms/{room_id}/presence") as pres1:
        with client.websocket_connect(f"/rooms/{room_id}/presence") as pres2:
            with client.websocket_connect(f"/peerjs?id={peer['peer_id']}") as ws:
                ws.receive_json()  # OPEN

                msg1 = pres1.receive_json()
                msg2 = pres2.receive_json()

                assert msg1["payload"]["kind"] == "joined"
                assert msg2["payload"]["kind"] == "joined"
