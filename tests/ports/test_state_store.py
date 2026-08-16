"""Проверяет контракт хранилища состояния и поведение фейка."""

from tests.fakes.state_store import FakeStateStore
from torrcast.domain.playback_state import PlaybackState
from torrcast.ports.state_store import StateStore


def test_fake_saves_loads_and_records_state() -> None:
    state = PlaybackState("movie", 12.5)
    fake = FakeStateStore()
    port: StateStore = fake
    port.save(state)
    assert port.load("movie") == state
    assert (fake.saved, fake.loaded) == ([state], ["movie"])
