"""Сверка карты с прогоном ложится на полку: следующий показ файла прогон не поднимает."""

from __future__ import annotations

import inspect

from torrcast.adapters.stream_pack.agreed_keys import agreed_keys
from torrcast.adapters.stream_pack.grid_for import grid_for
from torrcast.domain.film_keys import FilmKeys

URL = "http://торрент/поток?link=0123456789abcdef&index=0"

#: Ровный GOP в две секунды на минуту фильма.
KEYS = FilmKeys(60.0, [k * 2.0 for k in range(31)], [k * (2 << 20) for k in range(31)], "mkv")


class Pilot:
    """Подделка пробного прогона: отвечает названным вердиктом и считает запуски."""

    def __init__(self, verdict: bool) -> None:
        self.verdict, self.calls = verdict, 0

    def __call__(self, url: str, at: float, keys: FilmKeys) -> bool:
        self.calls += 1
        return self.verdict


def test_the_next_show_of_the_file_takes_the_agreed_map_from_the_shelf() -> None:
    """🔴 Показ - отдельный процесс: сверка прошлого показа не должна меряться снова."""
    first, second = Pilot(True), Pilot(True)

    assert agreed_keys(URL, 20.0, KEYS, agree=first) is True
    assert agreed_keys(URL, 20.0, KEYS, agree=second) is True

    assert (first.calls, second.calls) == (1, 0)


def test_another_boundary_or_another_map_asks_the_run_again() -> None:
    agreed_keys(URL, 20.0, KEYS, agree=Pilot(True))
    moved, redrawn = Pilot(True), Pilot(True)
    shifted = FilmKeys(60.0, [k * 2.0 + 1.0 for k in range(30)], list(KEYS.offset[:30]), "mkv")

    agreed_keys(URL, 30.0, KEYS, agree=moved)
    agreed_keys(URL, 20.0, shifted, agree=redrawn)

    assert (moved.calls, redrawn.calls) == (1, 1)


def test_a_map_that_did_not_agree_is_not_trusted_next_time() -> None:
    first, second = Pilot(False), Pilot(True)

    assert agreed_keys(URL, 20.0, KEYS, agree=first) is False
    assert agreed_keys(URL, 20.0, KEYS, agree=second) is True

    assert second.calls == 1


def test_the_grid_of_a_show_asks_the_shelf_before_the_run() -> None:
    assert inspect.signature(grid_for).parameters["agree_of"].default is agreed_keys
