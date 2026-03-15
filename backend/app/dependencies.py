"""FastAPI dependency providers."""
from __future__ import annotations

from starlette.requests import HTTPConnection

from app.event_log import EventLog
from app.connection_manager import ConnectionManager


def get_connection_manager(request: HTTPConnection) -> ConnectionManager:
    return request.app.state.connection_manager


def get_event_log(request: HTTPConnection) -> EventLog:
    return request.app.state.event_log
