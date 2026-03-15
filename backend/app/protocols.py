"""Structural protocols for WebSocket-like objects.

Using Protocols instead of the concrete Starlette ``WebSocket`` keeps the
core connection/event code decoupled from the HTTP framework and lets tests
pass lightweight in-process stubs without any mocking framework.
"""
from __future__ import annotations

from typing import Protocol


class SubscriberLike(Protocol):
    """Minimal interface for objects that can receive text messages.

    Used by ``EventLog`` for dashboard WebSocket subscribers, which only
    need ``send_text`` — the log never calls ``close`` on them.
    """

    async def send_text(self, data: str) -> None: ...


class WebsocketProtocol(SubscriberLike, Protocol):
    """Full peer/presence WebSocket interface.

    Extends ``SubscriberLike`` with ``close`` for use by
    ``ConnectionManager``, which must be able to forcibly terminate
    connections during heartbeat eviction and room teardown.
    """

    async def close(self) -> None: ...
