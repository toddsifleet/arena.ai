"""Shared test fixtures."""
import pytest
from starlette.testclient import TestClient

from app.dependencies import get_event_log, get_connection_manager
from app.event_log import EventLog
from app.main import app
from app.connection_manager import ConnectionManager
from app.connection_store import ConnectionStore


@pytest.fixture
def test_connection_manager():
    return ConnectionManager(store=ConnectionStore())


@pytest.fixture
def test_event_log():
    return EventLog()


@pytest.fixture
def client(test_connection_manager, test_event_log):
    test_event_log.subscribe_to_connection_manager(test_connection_manager)
    app.dependency_overrides[get_connection_manager] = lambda: test_connection_manager
    app.dependency_overrides[get_event_log] = lambda: test_event_log
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_connection_manager, None)
    app.dependency_overrides.pop(get_event_log, None)
