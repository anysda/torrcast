"""Порт состояния просмотра: договор целого состояния и назначенное хранилище."""

from __future__ import annotations

from tests.fakes.state_store import FakeStateStore
from torrcast.domain.entry import Entry
from torrcast.domain.watch_state import WatchState
from torrcast.ports.state_store.slot import install, store
from torrcast.ports.state_store.state_store import StateStore


def test_what_the_root_installed_is_what_the_scenarios_read() -> None:
    """Назначенное хранилище и отдаётся сценариям: тем же читают, что положили."""
    install(FakeStateStore())
    port: StateStore = store()

    state = port.load()
    state.put("movie:моана-2:2024", Entry(title="Моана 2", magnet="magnet:?xt=1", pos=12.5))
    port.save(state)

    assert store().load().entries["movie:моана-2:2024"].pos == 12.5


def test_the_state_is_read_and_written_whole() -> None:
    """Договор снят с настоящего вызова: целиком прочитать, целиком записать.

    Частями нельзя намеренно: рядом пишет другой ход показа, и запись по одному ключу
    затёрла бы его правку. Поэтому назначенному хранилищу отдают всё состояние, а не
    одну запись.
    """

    class _Spy:
        def __init__(self) -> None:
            self.saved: list[WatchState] = []
            self.state = WatchState()

        def load(self) -> WatchState:
            return self.state

        def save(self, state: WatchState) -> None:
            self.saved.append(state)
            self.state = state

    spy = _Spy()
    install(spy)

    whole = store().load()
    whole.put("movie:матрица:1999", Entry(title="Матрица", magnet="magnet:?xt=2", pos=1.0))
    store().save(whole)

    assert spy.saved == [whole], "хранилищу отдают состояние целиком, а не одну запись"
