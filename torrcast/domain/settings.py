"""Immutable application settings supplied to use cases as a value."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class Settings:
    """Configuration needed by scenarios, independent of its source."""

    tv: str | None = None
    receiver: Literal["chromecast", "mock"] = "chromecast"
    receiver_profile: str = ""
    torrserver_url: str = "http://127.0.0.1:8090"
    prowlarr_url: str = "http://127.0.0.1:9696"
    prowlarr_apikey: str = ""
    transport: Literal["http", "https"] = "http"
    hls_base_url: str = ""
    hls_port: int = 8080
    hls_cert: str = "/etc/torrcast/tls/torrcast.crt"
    hls_key: str = "/etc/torrcast/tls/torrcast.key"
    hls_dir: str = "/dev/shm/torrcast"
    state_path: str = "/var/lib/torrcast/state.json"
    trace: bool = False
