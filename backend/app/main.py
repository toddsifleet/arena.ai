"""MiniRTC signaling backend: FastAPI app and route wiring."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.connection_store import ConnectionStore
from app.event_log import EventLog
from app.connection_manager import ConnectionManager
from app.settings import settings
from app.routes import dashboard, health, presence, rooms, signaling


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup: start heartbeat task. Shutdown: cancel task, close all peer connections, then registry."""
    app.state.registry = ConnectionManager(store=ConnectionStore())
    app.state.event_log = EventLog(maxlen=200)
    app.state.event_log.subscribe_to_registry(app.state.registry)
    task = asyncio.create_task(app.state.registry.heartbeat_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await app.state.registry.close_all_peer_connections()
    await app.state.registry.shutdown()


app = FastAPI(
    title="MiniRTC Signaling",
    description="PeerJS-compatible signaling for 1:1 calls; media stays P2P.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["health"])
app.include_router(rooms.router, prefix="/rooms", tags=["rooms"])
app.include_router(presence.router, prefix="/rooms", tags=["presence"])
app.include_router(signaling.router, prefix="", tags=["signaling"])
app.include_router(dashboard.router, prefix="", tags=["dashboard"])
