"""Address of an HTTP server exposed to a playback receiver."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ServerAddress:
    """Public base URL of a started server."""

    base_url: str
