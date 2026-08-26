"""Проверяет выбор сетки для файла: по карте, ровная при беде, и что она говорит вслух."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from torrcast.adapters.stream_pack._keys_shelf import _keys_cache
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.grid_for import grid_for
from torrcast.adapters.stream_pack.read_keys import read_keys
from torrcast.adapters.stream_pack.refused_keys import refused_keys
from torrcast.domain.film_keys import FilmKeys
from torrcast.domain.hls_settings import MAX_SEGMENT_BYTES
from torrcast.domain.infra_error import InfraError

DAY = 24 * 60 * 60.0

#: Ровный GOP в две секунды на минуту фильма и ровный битрейт 2 МБ/с.
KEYS = FilmKeys(
    60.0, [round(k * 2.0, 3) for k in range(31)], [k * (2 << 20) for k in range(31)], "mkv"
)

#: Начало ленты меряет ffprobe; тут проверяется выбор сетки, а не замер, поэтому оно
#: приезжает готовым числом - и остаётся видимым в проверках, а не спрятанным в фикстуру.
ORIGIN = 0.083


def _agreed(url: str, at: float, keys: FilmKeys) -> bool:
    """Сверка карты с фактом сошлась: пробный прогон ffmpeg тут не поднимается."""
    return True


def _grid(
    keys: Callable[[str], FilmKeys],
    say: Callable[[str], None] | None = None,
    delivered_mbit: float = 0.0,
    cap: float = MAX_SEGMENT_BYTES,
    span_cap: float = 0.0,
) -> Grid:
    """Сетка по названной карте: обе зависимости приезжают договором :func:`grid_for`."""
    return grid_for(
        "http://торрент/поток",
        60.0,
        10.0,
        say=say,
        delivered_mbit=delivered_mbit,
        cap=cap,
        span_cap=span_cap,
        keys_of=keys,
        origin_of=lambda url: ORIGIN,
        agree_of=_agreed,
    )


def test_the_grid_stands_on_keyframes_when_the_map_was_taken() -> None:
    """Карта снялась - границы стоят на опорных кадрах, и каждый кусок самостоятелен."""
    grid = grid_for(
        "http://торрент/поток",
        60.0,
        10.0,
        keys_of=lambda url: KEYS,
        origin_of=lambda url: ORIGIN,
        agree_of=_agreed,
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
        "http://торрент/поток",
        0.0,
        10.0,
        keys_of=lambda url: KEYS,
        origin_of=lambda url: ORIGIN,
        agree_of=_agreed,
    )
    assert grid.duration == KEYS.duration


def test_a_heavier_ceiling_of_the_piece_makes_the_pieces_shorter() -> None:
    """Потолок веса куска у каждого приёмника свой, и сетка обязана его слушать."""
    wide = _grid(lambda url: KEYS, delivered_mbit=16.0)
    tight = _grid(lambda url: KEYS, delivered_mbit=16.0, cap=4.0e6)
    assert tight.count > wide.count, "потолок веса не укоротил куски"


def test_a_receiver_with_more_room_gets_fewer_and_heavier_pieces() -> None:
    """Измеренный запас приёмника заполняется, а осторожная сетка не сдвигается.

    Карта и паспорт одни и те же. Различается только потолок веса приёмника, поэтому
    проверка краснеет ровно тогда, когда этот потолок доходит до сетки, но не участвует
    в выборе границ.
    """
    heavy = FilmKeys(KEYS.duration, KEYS.at, [k * (4 << 20) for k in range(31)], KEYS.kind)
    cautious = _grid(lambda url: heavy, delivered_mbit=16.0, cap=16_000_000)
    roomy = _grid(lambda url: heavy, delivered_mbit=16.0, cap=28_000_000)

    assert cautious.bounds == (0.0, 6.0, 12.0, 18.0, 24.0, 30.0, 36.0, 42.0, 48.0, 54.0)
    assert roomy.bounds == (0.0, 12.0, 24.0, 36.0, 48.0)
    assert roomy.count < cautious.count
    assert roomy.weigh is not None and cautious.weigh is not None
    assert max(roomy.weigh(roomy.start(k), roomy.end(k)) for k in range(roomy.count - 1)) > max(
        cautious.weigh(cautious.start(k), cautious.end(k)) for k in range(cautious.count - 1)
    )


def test_more_room_does_not_stretch_a_piece_that_already_fit_the_cautious_cap() -> None:
    """Измерен вес, а не новая длительность: лёгкий кусок остаётся у прежнего шага."""
    cautious = _grid(lambda url: KEYS, delivered_mbit=16.0, cap=16_000_000)
    roomy = _grid(lambda url: KEYS, delivered_mbit=16.0, cap=28_000_000)

    assert roomy.bounds == cautious.bounds


def test_the_length_ceiling_of_the_receiver_reaches_the_grid() -> None:
    """Потолок длины - свойство приёмника, и он обязан доехать до границ, а не осесть в пути.

    Карта и паспорт одни и те же; различается ровно потолок длины, поэтому проверка
    краснеет тогда, когда он до сетки не доходит.
    """
    sparse = FilmKeys(60.0, [round(k * 6.0, 3) for k in range(11)], [], "mkv")

    free = _grid(lambda url: sparse)
    tight = _grid(lambda url: sparse, span_cap=8.0)

    assert max(free.span(k) for k in range(free.count - 1)) == 12.0
    assert max(tight.span(k) for k in range(tight.count - 1)) == 6.0


def test_a_map_that_disagreed_with_the_run_is_not_the_grid_of_the_show(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🔴 Сетка, признанная не сошедшейся с фактом, не имеет права остаться сеткой показа.

    Боевая запись 26-08: ``сверка карты с прогоном: сошлось false, карта 18.932, факт
    50.917`` - и сетка ``покадрам: true`` на 741 сегмент по этой самой карте осталась
    сеткой показа до конца вечера, потому что сверка стояла ПОСЛЕ постройки. Мера здесь
    отрицательная в обе стороны: та же карта при сошедшейся сверке даёт сетку по кадрам,
    при разошедшейся - ровную.
    """
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    said: list[str] = []
    asked: list[float] = []

    def apart(url: str, at: float, keys: FilmKeys) -> bool:
        asked.append(at)
        return False

    grid = grid_for(
        "http://торрент/поток",
        60.0,
        10.0,
        say=said.append,
        keys_of=lambda url: KEYS,
        origin_of=lambda url: ORIGIN,
        agree_of=apart,
    )

    assert grid.on_keys is False and grid.origin == ORIGIN
    assert said and "разошлась с прогоном" in said[-1]
    assert asked == [10.0], "сверять надо ПЕРВУЮ границу сетки, ту, что упаковка возьмёт первой"
    assert _grid(lambda url: KEYS).on_keys is True, "сошедшаяся сверка обязана оставить кадры"


def test_a_map_the_run_disagreed_with_does_not_wait_for_the_next_show(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Вердикт ложится на полку: иначе следующий показ снимет ту же карту и построит то же.

    Пробы честности судят индекс по байтам, а тут его судил факт по живому файлу - и без
    записи вердикта завтрашний сеанс повторил бы вчерашний.
    """
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    url = "http://торрент/поток"

    grid_for(
        url,
        60.0,
        10.0,
        keys_of=lambda source: KEYS,
        origin_of=lambda source: ORIGIN,
        agree_of=lambda source, at, keys: False,
    )

    assert refused_keys(_keys_cache(url), DAY) is not None, "вердикт не лёг на полку"
    assert read_keys(_keys_cache(url)) is None, "карта пережила вердикт"


def test_a_map_that_stops_before_the_film_ends_is_not_a_grid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🔴 Хвост за последним кадром карты резать НЕЧЕМ - он уезжает одним куском.

    «Матрица» 1999: последняя точка Cues 7778.899 при длительности 8175.488 - кусок
    396.6 с, то есть ``EXT-X-TARGETDURATION: 397`` при обещанных 10.5 с. Мерка своя у
    каждой карты: хвост судится самой широкой дырой внутри неё
    (:data:`~torrcast.domain.keys_tail_gaps.KEYS_TAIL_GAPS`).
    """
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    said: list[str] = []
    #: Шаг кадров 2 с, а кино идёт минуту: последний кадр на 40-й секунде - хвост 20 с.
    short = FilmKeys(60.0, [round(k * 2.0, 3) for k in range(21)], [], "mkv")
    #: Тот же шаг, тот же хвост в долях дыры на пределе - карта обязана остаться сеткой.
    whole = FilmKeys(60.0, [round(k * 2.0, 3) for k in range(26)], [], "mkv")

    assert _grid(lambda url: short, say=said.append).on_keys is False
    assert said and "хвост резать нечем" in said[-1] and "20.0 с до конца" in said[-1]
    assert _grid(lambda url: whole).on_keys is True, "здоровый хвост отвергнут вместе с битым"
