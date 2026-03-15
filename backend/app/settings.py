"""Configuration from environment."""
from __future__ import annotations

from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MINIRTC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server
    host: str = "0.0.0.0"
    port: int = 9000

    # CORS origins for REST/HTTP (comma-separated)
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Signaling WebSocket path (PeerJS client uses this as path)
    signaling_path: str = "/peerjs"

    # Heartbeat: interval in seconds for server->client ping, timeout to evict peer
    heartbeat_interval_seconds: float = 5.0
    heartbeat_timeout_seconds: float = 15.0

    # Reconnect: grace period in seconds before treating disconnect as final.
    # 10 s was too short for a WiFi→cellular handoff: the OS can take several
    # seconds to switch networks, and the signaling reconnect adds more latency
    # on top. 30 s gives the client enough runway to reconnect on a slow cell
    # network without holding the slot forever.
    reconnect_grace_seconds: float = 30.0

    # Empty room cleanup: remove unjoined rooms after this TTL
    empty_room_ttl_seconds: float = 300.0

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
