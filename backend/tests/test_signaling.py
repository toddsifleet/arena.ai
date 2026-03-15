"""Tests for WebSocket signaling."""


def _join(client, room_id):
    """Join a room via REST, return the response dict."""
    return client.get(f"/rooms/{room_id}/join").json()


def test_open_message(client):
    room_id = client.post("/rooms").json()["room_id"]
    peer = _join(client, room_id)
    with client.websocket_connect(f"/peerjs?id={peer['peer_id']}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "OPEN"
        assert msg["payload"]["id"] == peer["peer_id"]


def test_rejects_unknown_peer(client):
    with client.websocket_connect("/peerjs?id=not-a-real-peer-id-at-all") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "ERROR"


def test_rejects_missing_id(client):
    with client.websocket_connect("/peerjs") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "ERROR"


def test_open_emits_ws_connected_event(client, test_event_log):
    room_id = client.post("/rooms").json()["room_id"]
    peer = client.get(f"/rooms/{room_id}/join").json()
    with client.websocket_connect(f"/peerjs?id={peer['peer_id']}") as ws:
        ws.receive_json()  # OPEN
    types = [e.type for e in test_event_log.get_events()]
    assert "ws.connected" in types


def test_heartbeat_response(client):
    room_id = client.post("/rooms").json()["room_id"]
    peer = _join(client, room_id)
    with client.websocket_connect(f"/peerjs?id={peer['peer_id']}") as ws:
        ws.receive_json()  # OPEN
        ws.send_json({"type": "HEARTBEAT"})
        msg = ws.receive_json()
        assert msg["type"] == "HEARTBEAT"


def test_presence_on_join(client):
    room_id = client.post("/rooms").json()["room_id"]
    peer_a = _join(client, room_id)
    peer_b = _join(client, room_id)

    with client.websocket_connect(f"/peerjs?id={peer_a['peer_id']}") as ws_a:
        ws_a.receive_json()  # OPEN for peer_a

        with client.websocket_connect(f"/peerjs?id={peer_b['peer_id']}") as ws_b:
            ws_b.receive_json()  # OPEN for peer_b

            presence = ws_a.receive_json()
            assert presence["type"] == "PRESENCE"
            assert presence["payload"]["kind"] == "joined"
            assert presence["payload"]["peer_id"] == peer_b["peer_id"]


def test_presence_on_disconnect(client):
    """When peer_b's WS closes without LEAVE, peer_a receives PRESENCE(disconnected)."""
    room_id = client.post("/rooms").json()["room_id"]
    peer_a = _join(client, room_id)
    peer_b = _join(client, room_id)

    with client.websocket_connect(f"/peerjs?id={peer_a['peer_id']}") as ws_a:
        ws_a.receive_json()  # OPEN

        with client.websocket_connect(f"/peerjs?id={peer_b['peer_id']}") as ws_b:
            ws_b.receive_json()  # OPEN
            ws_a.receive_json()  # PRESENCE: peer_b joined

        # ws_b context exits — implicit disconnect
        presence = ws_a.receive_json()
        assert presence["type"] == "PRESENCE"
        assert presence["payload"]["kind"] == "disconnected"
        assert presence["payload"]["peer_id"] == peer_b["peer_id"]


def test_disconnect_emits_ws_disconnected_event(client, test_event_log):
    room_id = client.post("/rooms").json()["room_id"]
    peer = client.get(f"/rooms/{room_id}/join").json()
    with client.websocket_connect(f"/peerjs?id={peer['peer_id']}") as ws:
        ws.receive_json()  # OPEN
    types = [e.type for e in test_event_log.get_events()]
    assert "ws.disconnected" in types


def test_offer_forwarding(client):
    room_id = client.post("/rooms").json()["room_id"]
    peer_a = _join(client, room_id)
    peer_b = _join(client, room_id)

    with client.websocket_connect(f"/peerjs?id={peer_a['peer_id']}") as ws_a:
        ws_a.receive_json()  # OPEN

        with client.websocket_connect(f"/peerjs?id={peer_b['peer_id']}") as ws_b:
            ws_b.receive_json()  # OPEN
            ws_b.receive_json()  # PRESENCE (peer_a already connected)
            ws_a.receive_json()  # PRESENCE (peer_b joined)

            ws_a.send_json({
                "type": "OFFER",
                "dst": peer_b["peer_id"],
                "payload": {"sdp": "test-sdp"},
            })
            msg = ws_b.receive_json()
            assert msg["type"] == "OFFER"
            assert msg["src"] == peer_a["peer_id"]
            assert msg["payload"]["sdp"] == "test-sdp"


def test_answer_forwarding(client):
    room_id = client.post("/rooms").json()["room_id"]
    peer_a = _join(client, room_id)
    peer_b = _join(client, room_id)

    with client.websocket_connect(f"/peerjs?id={peer_a['peer_id']}") as ws_a:
        ws_a.receive_json()  # OPEN

        with client.websocket_connect(f"/peerjs?id={peer_b['peer_id']}") as ws_b:
            ws_b.receive_json()  # OPEN
            ws_a.receive_json()  # PRESENCE

            ws_b.send_json({
                "type": "ANSWER",
                "dst": peer_a["peer_id"],
                "payload": {"sdp": "answer-sdp"},
            })
            msg = ws_a.receive_json()
            assert msg["type"] == "ANSWER"
            assert msg["src"] == peer_b["peer_id"]


def test_candidate_forwarding(client):
    """CANDIDATE message is forwarded to the destination peer with src injected."""
    room_id = client.post("/rooms").json()["room_id"]
    peer_a = _join(client, room_id)
    peer_b = _join(client, room_id)

    with client.websocket_connect(f"/peerjs?id={peer_a['peer_id']}") as ws_a:
        ws_a.receive_json()  # OPEN

        with client.websocket_connect(f"/peerjs?id={peer_b['peer_id']}") as ws_b:
            ws_b.receive_json()  # OPEN
            ws_b.receive_json()  # PRESENCE (peer_a already connected)
            ws_a.receive_json()  # PRESENCE (peer_b joined)

            ws_a.send_json({
                "type": "CANDIDATE",
                "dst": peer_b["peer_id"],
                "payload": {"candidate": "ice-candidate-string"},
            })
            msg = ws_b.receive_json()
            assert msg["type"] == "CANDIDATE"
            assert msg["src"] == peer_a["peer_id"]
            assert msg["payload"]["candidate"] == "ice-candidate-string"


def test_offer_emits_signal_event(client, test_event_log):
    room_id = client.post("/rooms").json()["room_id"]
    peer_a = client.get(f"/rooms/{room_id}/join").json()
    peer_b = client.get(f"/rooms/{room_id}/join").json()

    with client.websocket_connect(f"/peerjs?id={peer_a['peer_id']}") as ws_a:
        ws_a.receive_json()
        with client.websocket_connect(f"/peerjs?id={peer_b['peer_id']}") as ws_b:
            ws_b.receive_json()
            ws_a.receive_json()  # PRESENCE
            ws_a.send_json({"type": "OFFER", "dst": peer_b["peer_id"], "payload": {"sdp": "x"}})
            ws_b.receive_json()  # forwarded offer

    types = [e.type for e in test_event_log.get_events()]
    assert "signal.offer" in types


def test_ignores_offer_to_unknown_dst(client):
    """OFFER to a peer not in the room is silently dropped."""
    room_id = client.post("/rooms").json()["room_id"]
    peer_a = _join(client, room_id)

    with client.websocket_connect(f"/peerjs?id={peer_a['peer_id']}") as ws_a:
        ws_a.receive_json()  # OPEN
        ws_a.send_json({
            "type": "OFFER",
            "dst": "nonexistent-peer",
            "payload": {"sdp": "test"},
        })
        # Send a heartbeat to confirm the connection is still alive
        ws_a.send_json({"type": "HEARTBEAT"})
        msg = ws_a.receive_json()
        assert msg["type"] == "HEARTBEAT"


def test_ignores_offer_without_dst(client):
    """OFFER with no dst field is silently ignored."""
    room_id = client.post("/rooms").json()["room_id"]
    peer_a = _join(client, room_id)

    with client.websocket_connect(f"/peerjs?id={peer_a['peer_id']}") as ws_a:
        ws_a.receive_json()  # OPEN
        ws_a.send_json({"type": "OFFER", "payload": {"sdp": "sdp"}})
        # Connection stays alive
        ws_a.send_json({"type": "HEARTBEAT"})
        assert ws_a.receive_json()["type"] == "HEARTBEAT"


def test_ignores_invalid_json(client):
    """Non-JSON text is silently ignored; the connection stays alive."""
    room_id = client.post("/rooms").json()["room_id"]
    peer_a = _join(client, room_id)

    with client.websocket_connect(f"/peerjs?id={peer_a['peer_id']}") as ws_a:
        ws_a.receive_json()  # OPEN
        ws_a.send_text("this is not json }{")
        ws_a.send_json({"type": "HEARTBEAT"})
        assert ws_a.receive_json()["type"] == "HEARTBEAT"


def test_leave_removes_peer_from_room(client):
    """LEAVE message causes the peer to be removed from the room."""
    room_id = client.post("/rooms").json()["room_id"]
    peer_a = _join(client, room_id)

    with client.websocket_connect(f"/peerjs?id={peer_a['peer_id']}") as ws_a:
        ws_a.receive_json()  # OPEN
        ws_a.send_json({"type": "LEAVE"})

    # Peer should be gone from the room
    peers = client.get(f"/rooms/{room_id}/peers").json()["peers"]
    assert len(peers) == 0


def test_leave_notifies_other_peer(client):
    """When peer_a sends LEAVE, peer_b receives PRESENCE(left)."""
    room_id = client.post("/rooms").json()["room_id"]
    peer_a = _join(client, room_id)
    peer_b = _join(client, room_id)

    with client.websocket_connect(f"/peerjs?id={peer_b['peer_id']}") as ws_b:
        ws_b.receive_json()  # OPEN

        with client.websocket_connect(f"/peerjs?id={peer_a['peer_id']}") as ws_a:
            ws_a.receive_json()  # OPEN
            ws_b.receive_json()  # PRESENCE: peer_a joined

            ws_a.send_json({"type": "LEAVE"})

        # ws_a context exited after LEAVE; server finalises the disconnect
        presence = ws_b.receive_json()
        assert presence["type"] == "PRESENCE"
        assert presence["payload"]["kind"] == "left"
        assert presence["payload"]["peer_id"] == peer_a["peer_id"]


def test_leave_emits_peer_left_event(client, test_event_log):
    room_id = client.post("/rooms").json()["room_id"]
    peer = client.get(f"/rooms/{room_id}/join").json()

    with client.websocket_connect(f"/peerjs?id={peer['peer_id']}") as ws:
        ws.receive_json()  # OPEN
        ws.send_json({"type": "LEAVE"})

    types = [e.type for e in test_event_log.get_events()]
    assert "peer.left" in types


def test_reconnect_sends_reconnected_presence(client):
    """Re-connecting after a drop emits PRESENCE(reconnected) to the other peer."""
    room_id = client.post("/rooms").json()["room_id"]
    peer_a = _join(client, room_id)
    peer_b = _join(client, room_id)

    with client.websocket_connect(f"/peerjs?id={peer_b['peer_id']}") as ws_b:
        ws_b.receive_json()  # OPEN

        # peer_a connects then drops
        with client.websocket_connect(f"/peerjs?id={peer_a['peer_id']}") as ws_a:
            ws_a.receive_json()  # OPEN
            ws_b.receive_json()  # PRESENCE: joined

        ws_b.receive_json()  # PRESENCE: disconnected

        # peer_a re-joins with same client_id
        rejoin = client.get(f"/rooms/{room_id}/join?client_id={peer_a['client_id']}").json()
        assert rejoin["peer_id"] == peer_a["peer_id"]

        # peer_a reconnects via WS
        with client.websocket_connect(f"/peerjs?id={peer_a['peer_id']}") as ws_a2:
            ws_a2.receive_json()  # OPEN

            presence = ws_b.receive_json()
            assert presence["type"] == "PRESENCE"
            assert presence["payload"]["kind"] == "reconnected"
            assert presence["payload"]["peer_id"] == peer_a["peer_id"]
