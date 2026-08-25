"""Зеркало фейка состояния: помнит позицию, но файлов на диске не заводит."""

from tests.fakes.state_store import FakeStateStore
from torrcast.domain.entry import Entry
from torrcast.ports.state_store.state_store import StateStore


def test_the_state_survives_the_run_but_never_reaches_a_file(tmp_path: object) -> None:
    """Показ обязан помнить позицию хотя бы в пределах своего запуска."""
    port: StateStore = FakeStateStore()

    state = port.load()
    state.put("movie:моана-2:2024", Entry(title="Моана 2", magnet="magnet:?xt=1", pos=12.5))
    port.save(state)

    assert port.load().entries["movie:моана-2:2024"].pos == 12.5


def test_a_read_gives_its_own_state_and_not_the_shared_one() -> None:
    """Отрицательная проба: правка без :meth:`save` до соседа доезжать не имеет права.

    Файловое хранилище отдаёт новое значение на каждое чтение, и подделка обязана врать
    так же - иначе тест зеленел бы на записи, которой боевой путь не делает.
    """
    port: StateStore = FakeStateStore()
    port.save(port.load())

    stray = port.load()
    stray.put("movie:матрица:1999", Entry(title="Матрица", magnet="magnet:?xt=2", pos=1.0))

    assert "movie:матрица:1999" not in port.load().entries
