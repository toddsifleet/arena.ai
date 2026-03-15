"""Shared test fixtures."""
import pytest
from starlette.testclient import TestClient

from app.dependencies import get_event_log, get_registry
from app.event_log import EventLog
from app.main import app
from app.connection_manager import ConnectionManager
from app.connection_store import ConnectionStore


@pytest.fixture
def test_registry():
    """A fresh ConnectionManager instance."""
    return ConnectionManager(store=ConnectionStore())


@pytest.fixture
def test_event_log():
    """A fresh EventLog instance."""
    return EventLog()


@pytest.fixture
def client(test_registry, test_event_log):
    """Starlette test client wired to the test_registry and test_event_log fixtures."""
    test_event_log.subscribe_to_registry(test_registry)
    app.dependency_overrides[get_registry] = lambda: test_registry
    app.dependency_overrides[get_event_log] = lambda: test_event_log
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_registry, None)
    app.dependency_overrides.pop(get_event_log, None)
