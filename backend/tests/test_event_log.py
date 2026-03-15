"""Unit tests for the EventLog circular buffer."""
import json

import pytest

from app.event_log import EventLog


@pytest.mark.asyncio
async def test_emit_records_event():
    el = EventLog()
    event = await el.emit("test.event", {"key": "value"})
    assert event.type == "test.event"
    assert event.data == {"key": "value"}
    assert event.id == 1
    assert event.timestamp > 0


@pytest.mark.asyncio
async def test_emit_increments_id():
    el = EventLog()
    e1 = await el.emit("a", {})
    e2 = await el.emit("b", {})
    e3 = await el.emit("c", {})
    assert e1.id == 1
    assert e2.id == 2
    assert e3.id == 3


@pytest.mark.asyncio
async def test_get_events_returns_all():
    el = EventLog()
    await el.emit("x", {"n": 1})
    await el.emit("y", {"n": 2})
    events = el.get_events()
    assert len(events) == 2
    assert events[0].type == "x"
    assert events[1].type == "y"


@pytest.mark.asyncio
async def test_maxlen_truncation():
    """Oldest events are dropped once the buffer is full."""
    el = EventLog(maxlen=3)
    for i in range(5):
        await el.emit("e", {"i": i})
    events = el.get_events()
    assert len(events) == 3
    assert events[0].data["i"] == 2  # oldest kept
    assert events[-1].data["i"] == 4  # newest


@pytest.mark.asyncio
async def test_get_events_empty():
    assert EventLog().get_events() == []


@pytest.mark.asyncio
async def test_to_dict_shape():
    el = EventLog()
    event = await el.emit("room.created", {"room_id": "abc"})
    d = event.to_dict()
    assert set(d.keys()) == {"id", "type", "data", "timestamp"}
    assert d["type"] == "room.created"
    assert d["data"] == {"room_id": "abc"}


@pytest.mark.asyncio
async def test_subscribe_receives_events():
    el = EventLog()
    received: list[str] = []

    class FakeWS:
        async def send_text(self, data: str) -> None:
            received.append(data)

    el.subscribe(FakeWS())
    await el.emit("ping", {"msg": "hello"})

    assert len(received) == 1
    payload = json.loads(received[0])
    assert payload["type"] == "EVENT"
    assert payload["event"]["type"] == "ping"
    assert payload["event"]["data"]["msg"] == "hello"


@pytest.mark.asyncio
async def test_unsubscribe_stops_receiving():
    el = EventLog()
    received: list[str] = []

    class FakeWS:
        async def send_text(self, data: str) -> None:
            received.append(data)

    ws = FakeWS()
    el.subscribe(ws)
    el.unsubscribe(ws)
    await el.emit("ping", {})

    assert received == []


@pytest.mark.asyncio
async def test_multiple_subscribers_all_receive():
    el = EventLog()
    counts: dict[str, int] = {"a": 0, "b": 0}

    class FakeWS:
        def __init__(self, name: str) -> None:
            self.name = name

        async def send_text(self, _data: str) -> None:
            counts[self.name] += 1

    el.subscribe(FakeWS("a"))
    el.subscribe(FakeWS("b"))
    await el.emit("event", {})

    assert counts["a"] == 1
    assert counts["b"] == 1


@pytest.mark.asyncio
async def test_dead_subscriber_is_pruned():
    """A subscriber whose send_text raises is automatically removed."""
    el = EventLog()

    class DeadWS:
        async def send_text(self, _data: str) -> None:
            raise RuntimeError("connection closed")

    ws = DeadWS()
    el.subscribe(ws)
    assert ws in el._subscribers

    await el.emit("test", {})

    assert ws not in el._subscribers


@pytest.mark.asyncio
async def test_dead_subscriber_does_not_block_live_ones():
    """A failing subscriber does not prevent delivery to healthy ones."""
    el = EventLog()
    received: list[str] = []

    class DeadWS:
        async def send_text(self, _data: str) -> None:
            raise RuntimeError("dead")

    class LiveWS:
        async def send_text(self, data: str) -> None:
            received.append(data)

    el.subscribe(DeadWS())
    el.subscribe(LiveWS())
    await el.emit("test", {"value": 42})

    assert len(received) == 1
