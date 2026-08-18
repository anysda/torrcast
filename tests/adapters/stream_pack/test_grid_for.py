"""Проверяет выбор сетки для файла: по карте, ровная при беде, и что она говорит вслух."""

from __future__ import annotations

import pytest

from tests.conftest import module_of
from torrcast.adapters.stream_pack.grid_for import grid_for
from torrcast.domain.film_keys import FilmKeys
from torrcast.domain.infra_error import InfraError

module = module_of("torrcast.adapters.stream_pack.grid_for")

#: Ровный GOP в две секунды на минуту фильма и ровный битрейт 2 МБ/с.
KEYS = FilmKeys(
    60.0, [round(k * 2.0, 3) for k in range(31)], [k * (2 << 20) for k in range(31)], "mkv"
)


@pytest.fixture(autouse=True)
def _no_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Начало ленты меряет ffprobe; тут проверяется выбор сетки, а не замер."""
    monkeypatch.setattr(module, "pack_origin", lambda url: 0.083)


def test_the_grid_stands_on_keyframes_when_the_map_was_taken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Карта снялась - границы стоят на опорных кадрах, и каждый кусок самостоятелен."""
    monkeypatch.setattr(module, "film_keys", lambda url: KEYS)
    grid = grid_for("http://торрент/поток", 60.0, 10.0)
    assert grid.on_keys is True
    assert all(place in KEYS.at for place in grid.bounds)
    assert grid.origin == 0.083, "начало ленты обязано уехать в сетку"


def test_a_uniform_grid_is_never_a_silent_substitution(monkeypatch: pytest.MonkeyPatch) -> None:
    """🔴 Молчаливая подмена нарезки - ровно то, из-за чего подвис приёмника расследовали
    двое суток. Каждая подмена говорит вслух и называет причину.
    """
    said: list[str] = []

    monkeypatch.setattr(module, "film_keys", lambda url: KEYS)
    grid = grid_for("http://торрент/поток", 60.0, 10.0, on_keys=False, say=said.append)
    assert grid.on_keys is False and grid.origin == 0.083
    assert said and "так велено настройкой" in said[-1]

    def dead(url: str) -> FilmKeys:
        raise InfraError("индекса в контейнере нет")

    said.clear()
    monkeypatch.setattr(module, "film_keys", dead)
    grid = grid_for("http://торрент/поток", 60.0, 10.0, say=said.append)
    assert grid.on_keys is False and grid.origin == 0.083
    assert said and "индекса в контейнере нет" in said[-1]


def test_a_map_that_does_not_look_like_video_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """Три кадра на весь фильм или карта, кончающаяся на середине, - это не карта видео."""
    said: list[str] = []
    monkeypatch.setattr(module, "film_keys", lambda url: FilmKeys(60.0, [0.0, 2.0], [0, 1], "mkv"))
    assert grid_for("http://торрент/поток", 60.0, 10.0, say=said.append).on_keys is False

    half = FilmKeys(60.0, [0.0, 2.0, 4.0, 6.0], [0, 1, 2, 3], "mkv")
    monkeypatch.setattr(module, "film_keys", lambda url: half)
    assert grid_for("http://торрент/поток", 60.0, 10.0, say=said.append).on_keys is False
    assert all("не похожа на видео" in line for line in said)


def test_the_length_of_the_film_is_taken_from_the_map_when_it_is_not_known(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Паспорт молчит про длительность - её знает карта, и манифест обязан быть честным."""
    monkeypatch.setattr(module, "film_keys", lambda url: KEYS)
    assert grid_for("http://торрент/поток", 0.0, 10.0).duration == KEYS.duration


def test_a_heavier_ceiling_of_the_piece_makes_the_pieces_shorter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Потолок веса куска у каждого приёмника свой, и сетка обязана его слушать."""
    monkeypatch.setattr(module, "film_keys", lambda url: KEYS)
    wide = grid_for("http://торрент/поток", 60.0, 10.0, delivered_mbit=16.0)
    tight = grid_for("http://торрент/поток", 60.0, 10.0, delivered_mbit=16.0, cap=4.0e6)
    assert tight.count > wide.count, "потолок веса не укоротил куски"
