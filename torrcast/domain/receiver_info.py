"""Identity of a playback receiver discovered on the local network."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReceiverInfo:
    """Stable receiver details required to select and connect to it."""

    name: str
    address: str
    model: str = ""
