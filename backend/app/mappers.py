"""Functions that convert raw internal snapshot dicts to Pydantic response models."""
from __future__ import annotations

from app.schemas import (
    DashboardSnapshot,
    EventPayload,
    PeerSnap,
    SnapshotData,
    StatsSnap,
)


def build_snapshot(raw: SnapshotData, events: list[EventPayload] | None = None) -> str:
    """Convert a ``SnapshotData`` dict into a serialised ``DashboardSnapshot``."""
    rooms = {
        room_id: [PeerSnap(**p) for p in peers]
        for room_id, peers in raw["rooms"].items()
    }
    snap = DashboardSnapshot(
        rooms=rooms,
        stats=StatsSnap(**raw["stats"]),
        events=events,
    )
    return snap.model_dump_json()


def snapshot_to_dashboard(raw: SnapshotData, events: list[EventPayload] | None = None) -> DashboardSnapshot:
    """Convert a ``SnapshotData`` dict into a ``DashboardSnapshot`` model."""
    rooms = {
        room_id: [PeerSnap(**p) for p in peers]
        for room_id, peers in raw["rooms"].items()
    }
    return DashboardSnapshot(
        rooms=rooms,
        stats=StatsSnap(**raw["stats"]),
        events=events,
    )
