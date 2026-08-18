"""Проверяет выбор сетки для файла: по карте, ровная при беде, и что она говорит вслух."""

from __future__ import annotations

from collections.abc import Callable

from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.grid_for import grid_for
from torrcast.domain.film_keys import FilmKeys
from torrcast.domain.hls_settings import MAX_SEGMENT_BYTES
from torrcast.domain.infra_error import InfraError

#: Ровный GOP в две секунды на минуту фильма и ровный битрейт 2 МБ/с.
KEYS = FilmKeys(
    60.0, [round(k * 2.0, 3) for k in range(31)], [k * (2 << 20) for k in range(31)], "mkv"
)

#: Начало ленты меряет ffprobe; тут проверяется выбор сетки, а не замер, поэтому оно
#: приезжает готовым числом - и остаётся видимым в проверках, а не спрятанным в фикстуру.
ORIGIN = 0.083


def _grid(
    keys: Callable[[str], FilmKeys],
    say: Callable[[str], None] | None = None,
    delivered_mbit: float = 0.0,
    cap: float = MAX_SEGMENT_BYTES,
) -> Grid:
    """Сетка по названной карте: обе зависимости приезжают договором :func:`grid_for`."""
    return grid_for(
        "http://торрент/поток",
        60.0,
        10.0,
        say=say,
        delivered_mbit=delivered_mbit,
        cap=cap,
        keys_of=keys,
        origin_of=lambda url: ORIGIN,
    )


def test_the_grid_stands_on_keyframes_when_the_map_was_taken() -> None:
    """Карта снялась - границы стоят на опорных кадрах, и каждый кусок самостоятелен."""
    grid = grid_for(
        "http://торрент/поток", 60.0, 10.0, keys_of=lambda url: KEYS, origin_of=lambda url: ORIGIN
    )
    assert grid.on_keys is True
    assert all(place in KEYS.at for place in grid.bounds)
    assert grid.origin == ORIGIN, "начало ленты обязано уехать в сетку"


def test_a_uniform_grid_is_never_a_silent_substitution() -> None:
    """🔴 Молчаливая подмена нарезки - ровно то, из-за чего подвис приёмника расследовали
    двое суток. Каждая подмена говорит вслух и называет причину.
    """
    said: list[str] = []

    grid = grid_for(
        "http://торрент/поток",
        60.0,
        10.0,
        on_keys=False,
        say=said.append,
        keys_of=lambda url: KEYS,
        origin_of=lambda url: ORIGIN,
    )
    assert grid.on_keys is False and grid.origin == ORIGIN
    assert said and "так велено настройкой" in said[-1]

    def dead(url: str) -> FilmKeys:
        raise InfraError("индекса в контейнере нет")

    said.clear()
    grid = grid_for(
        "http://торрент/поток",
        60.0,
        10.0,
        say=said.append,
        keys_of=dead,
        origin_of=lambda url: ORIGIN,
    )
    assert grid.on_keys is False and grid.origin == ORIGIN
    assert said and "индекса в контейнере нет" in said[-1]


def test_a_map_that_does_not_look_like_video_is_refused() -> None:
    """Три кадра на весь фильм или карта, кончающаяся на середине, - это не карта видео."""
    said: list[str] = []
    thin = FilmKeys(60.0, [0.0, 2.0], [0, 1], "mkv")
    assert _grid(lambda url: thin, say=said.append).on_keys is False

    half = FilmKeys(60.0, [0.0, 2.0, 4.0, 6.0], [0, 1, 2, 3], "mkv")
    assert _grid(lambda url: half, say=said.append).on_keys is False
    assert all("не похожа на видео" in line for line in said)


def test_the_length_of_the_film_is_taken_from_the_map_when_it_is_not_known() -> None:
    """Паспорт молчит про длительность - её знает карта, и манифест обязан быть честным."""
    grid = grid_for(
        "http://торрент/поток", 0.0, 10.0, keys_of=lambda url: KEYS, origin_of=lambda url: ORIGIN
    )
    assert grid.duration == KEYS.duration


def test_a_heavier_ceiling_of_the_piece_makes_the_pieces_shorter() -> None:
    """Потолок веса куска у каждого приёмника свой, и сетка обязана его слушать."""
    wide = _grid(lambda url: KEYS, delivered_mbit=16.0)
    tight = _grid(lambda url: KEYS, delivered_mbit=16.0, cap=4.0e6)
    assert tight.count > wide.count, "потолок веса не укоротил куски"
