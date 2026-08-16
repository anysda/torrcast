"""Хранит в памяти состояние воспроизведения для тестов."""

from dataclasses import dataclass, field

from torrcast.domain.playback_state import PlaybackState


@dataclass
class FakeStateStore:
    states: dict[str, PlaybackState] = field(default_factory=dict)
    loaded: list[str] = field(default_factory=list)
    saved: list[PlaybackState] = field(default_factory=list)

    def load(self, key: str) -> PlaybackState | None:
        self.loaded.append(key)
        return self.states.get(key)

    def save(self, state: PlaybackState) -> None:
        self.saved.append(state)
        self.states[state.key] = state
