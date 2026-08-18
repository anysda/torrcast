"""Проверяет фоновый прогрев файла: порядок трёх дел и размер головы по контейнеру."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import pytest

from torrcast.adapters.stream_pack.warm_file import warm_file
from torrcast.domain.film_keys import FilmKeys
from torrcast.domain.warm_open import HEAD_OPEN, HEAD_WARM


@dataclass
class Watch:
    """Наблюдатель за прогревом: карта под рукой, а прогретые куски - списком.

    Голову греет :func:`pull_head`, место позиции - сам :func:`warm_file`, но работа у них
    одна, поэтому наблюдатель один: ``warm`` уезжает в оба места договором.
    """

    keys: FilmKeys | None
    asked: list[tuple[int, int]] = field(default_factory=list)

    def warm(self, url: str, offset: int, upto: int = 0, alive: Any = None) -> int:
        self.asked.append((offset, upto))
        return 0

    def keys_of(self, url: str) -> FilmKeys:
        if self.keys is None:
            raise OSError("карта не снялась")
        return self.keys

    def wait(self, count: int) -> None:
        """Дождаться, пока фоновый прогрев отчитается о нужном числе кусков."""
        for _ in range(300):
            if len(self.asked) >= count:
                return
            time.sleep(0.01)


@pytest.mark.machine
def test_from_the_start_only_the_head_is_warmed() -> None:
    """С нуля греется начало, и только оно: место позиции и есть начало."""
    watch = Watch(FilmKeys(600.0, [0.0, 200.0], [0, 500 << 20], "mp4"))
    warm_file("http://торрент/поток", keys_of=watch.keys_of, warm=watch.warm)
    watch.wait(1)
    time.sleep(0.1)
    assert watch.asked == [(0, HEAD_WARM)]


@pytest.mark.machine
def test_the_middle_warms_the_header_and_the_place_of_the_position() -> None:
    """Продолжение с середины греет заголовок и место позиции, а не 32 МБ чужого начала.

    Смещение берётся из карты: доля «позиция от длительности на размер файла» промахнулась
    бы на четверть фильма.
    """
    watch = Watch(FilmKeys(600.0, [0.0, 100.0, 200.0], [0, 90 << 20, 500 << 20], "mp4"))
    warm_file("http://торрент/поток", at=240.0, keys_of=watch.keys_of, warm=watch.warm)
    watch.wait(2)
    assert watch.asked == [(0, HEAD_OPEN["mp4"]), (500 << 20, HEAD_WARM)]


@pytest.mark.machine
def test_the_head_is_sized_by_the_container_of_the_map() -> None:
    """У mkv головы мало, у mp4 там ``moov``: греть их поровну - отнимать полосу у показа."""
    watch = Watch(FilmKeys(600.0, [0.0, 200.0], [0, 500 << 20], "mkv"))
    warm_file("http://торрент/поток", at=240.0, keys_of=watch.keys_of, warm=watch.warm)
    watch.wait(2)
    assert watch.asked[0] == (0, HEAD_OPEN["mkv"])


@pytest.mark.machine
def test_an_old_map_takes_the_container_from_the_name_of_the_file() -> None:
    """Карта из кэша прошлой версии контейнера не знает - его называет имя файла раздачи."""
    watch = Watch(FilmKeys(600.0, [0.0, 200.0], [0, 500 << 20], ""))
    warm_file(
        "http://торрент/поток?link=hash&index=1",
        at=240.0,
        name="Moana.2.2024.mkv",
        keys_of=watch.keys_of,
        warm=watch.warm,
    )
    watch.wait(2)
    assert watch.asked[0] == (0, HEAD_OPEN["mkv"])


@pytest.mark.machine
def test_a_map_that_did_not_come_still_warms_the_head() -> None:
    """Не вышло с картой - не беда: показ сделает то же самое сам, просто на своём времени."""
    watch = Watch(None)
    warm_file("http://торрент/поток", at=240.0, keys_of=watch.keys_of, warm=watch.warm)
    watch.wait(1)
    time.sleep(0.1)
    assert watch.asked == [(0, HEAD_WARM)], "без карты греть место позиции нечем"


@pytest.mark.machine
def test_a_release_the_show_gave_up_on_is_not_warmed_further() -> None:
    """Отвергнутый релиз дотягивать нельзя: он отъедает полосу у выбранного."""
    watch = Watch(FilmKeys(600.0, [0.0, 200.0], [0, 500 << 20], "mp4"))
    warm_file(
        "http://торрент/поток",
        at=240.0,
        alive=lambda: False,
        keys_of=watch.keys_of,
        warm=watch.warm,
    )
    time.sleep(0.2)
    assert watch.asked == [], "прогрев пошёл по релизу, от которого показ уже отказался"
