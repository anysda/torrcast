"""Проверяет фоновый прогрев файла: порядок трёх дел и размер головы по контейнеру."""

from __future__ import annotations

import time
from typing import Any

import pytest

from tests.conftest import module_of
from torrcast.adapters.stream_pack.warm_file import warm_file
from torrcast.domain.film_keys import FilmKeys
from torrcast.domain.warm_open import HEAD_OPEN, HEAD_WARM

module = module_of("torrcast.adapters.stream_pack.warm_file")
head_module = module_of("torrcast.adapters.stream_pack.pull_head")


def _watch(monkeypatch: pytest.MonkeyPatch, keys: FilmKeys | None) -> list[tuple[int, int]]:
    asked: list[tuple[int, int]] = []

    def note(url: str, offset: int, upto: int = 0, alive: Any = None) -> int:
        asked.append((offset, upto))
        return 0

    def map_of(url: str) -> FilmKeys:
        if keys is None:
            raise OSError("карта не снялась")
        return keys

    # Голову греет pull_head, место позиции - сам warm_file: подмену видят оба.
    monkeypatch.setattr(module, "warm_at", note)
    monkeypatch.setattr(head_module, "warm_at", note)
    monkeypatch.setattr(module, "film_keys", map_of)
    return asked


def _await(asked: list[tuple[int, int]], count: int) -> None:
    for _ in range(300):
        if len(asked) >= count:
            return
        time.sleep(0.01)


@pytest.mark.machine
def test_from_the_start_only_the_head_is_warmed(monkeypatch: pytest.MonkeyPatch) -> None:
    """С нуля греется начало, и только оно: место позиции и есть начало."""
    keys = FilmKeys(600.0, [0.0, 200.0], [0, 500 << 20], "mp4")
    asked = _watch(monkeypatch, keys)
    warm_file("http://торрент/поток")
    _await(asked, 1)
    time.sleep(0.1)
    assert asked == [(0, HEAD_WARM)]


@pytest.mark.machine
def test_the_middle_warms_the_header_and_the_place_of_the_position(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Продолжение с середины греет заголовок и место позиции, а не 32 МБ чужого начала.

    Смещение берётся из карты: доля «позиция от длительности на размер файла» промахнулась
    бы на четверть фильма.
    """
    keys = FilmKeys(600.0, [0.0, 100.0, 200.0], [0, 90 << 20, 500 << 20], "mp4")
    asked = _watch(monkeypatch, keys)
    warm_file("http://торрент/поток", at=240.0)
    _await(asked, 2)
    assert asked == [(0, HEAD_OPEN["mp4"]), (500 << 20, HEAD_WARM)]


@pytest.mark.machine
def test_the_head_is_sized_by_the_container_of_the_map(monkeypatch: pytest.MonkeyPatch) -> None:
    """У mkv головы мало, у mp4 там ``moov``: греть их поровну - отнимать полосу у показа."""
    keys = FilmKeys(600.0, [0.0, 200.0], [0, 500 << 20], "mkv")
    asked = _watch(monkeypatch, keys)
    warm_file("http://торрент/поток", at=240.0)
    _await(asked, 2)
    assert asked[0] == (0, HEAD_OPEN["mkv"])


@pytest.mark.machine
def test_an_old_map_takes_the_container_from_the_name_of_the_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Карта из кэша прошлой версии контейнера не знает - его называет имя файла раздачи."""
    keys = FilmKeys(600.0, [0.0, 200.0], [0, 500 << 20], "")
    asked = _watch(monkeypatch, keys)
    warm_file("http://торрент/поток?link=hash&index=1", at=240.0, name="Moana.2.2024.mkv")
    _await(asked, 2)
    assert asked[0] == (0, HEAD_OPEN["mkv"])


@pytest.mark.machine
def test_a_map_that_did_not_come_still_warms_the_head(monkeypatch: pytest.MonkeyPatch) -> None:
    """Не вышло с картой - не беда: показ сделает то же самое сам, просто на своём времени."""
    asked = _watch(monkeypatch, None)
    warm_file("http://торрент/поток", at=240.0)
    _await(asked, 1)
    time.sleep(0.1)
    assert asked == [(0, HEAD_WARM)], "без карты греть место позиции нечем"


@pytest.mark.machine
def test_a_release_the_show_gave_up_on_is_not_warmed_further(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Отвергнутый релиз дотягивать нельзя: он отъедает полосу у выбранного."""
    keys = FilmKeys(600.0, [0.0, 200.0], [0, 500 << 20], "mp4")
    asked = _watch(monkeypatch, keys)
    warm_file("http://торрент/поток", at=240.0, alive=lambda: False)
    time.sleep(0.2)
    assert asked == [], "прогрев пошёл по релизу, от которого показ уже отказался"
