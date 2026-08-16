"""Хранит между запусками состояние сценариев."""

from typing import Protocol

from torrcast.domain.playback_state import PlaybackState


class StateStore(Protocol):
    def load(self, key: str) -> PlaybackState | None: ...
    def save(self, state: PlaybackState) -> None: ...
