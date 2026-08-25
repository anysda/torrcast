"""Проверяет сетку сегментов: абсолютность границ, их поиск и манифест на весь фильм."""

import math

import pytest

from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.hls_manifest import hls_manifest
from torrcast.domain.hls_settings import GRID_WEIGHT_MARGIN, HLS_SEGMENT_SECONDS
from torrcast.domain.segment_container import FMP4


def test_fmp4_manifest_names_init_and_media_segments() -> None:
    """Общий заголовок назван, и это не украшение: без него приёмник качает куски, но
    разбор не начинает вовсе - конвейер стоит в ``kStarting`` (живой замер на приставке).
    """
    text = hls_manifest([10.0, 7.5], 10, True, FMP4)

    assert "#EXT-X-VERSION:7" in text
    assert '#EXT-X-MAP:URI="init.mp4"' in text
    assert "v0.m4s" in text and "v1.m4s" in text
    assert ".ts" not in text


def test_a_uniform_grid_starts_at_zero_and_keeps_the_step() -> None:
    """Граница - это число от нуля фильма, а не «сколько прошло от старта упаковки».

    Пока сетка была шагом, имя сегмента значило разное место фильма в зависимости от
    того, откуда начали паковать, и фаза после каждой перемотки становилась другой.
    """
    grid = Grid.uniform(60.0, 8.0)
    assert grid.bounds[0] == 0.0
    assert grid.bounds == (0.0, 8.0, 16.0, 24.0, 32.0, 40.0, 48.0)
    assert grid.duration == 60.0 and grid.on_keys is False


def test_a_short_tail_sticks_to_the_last_piece_and_a_short_film_is_one_piece() -> None:
    """Пара секунд отдельным куском в манифесте не стоит, а короткому кино хватает одного.

    Длительность при этом остаётся честной: приписать фильму лишние секунды значило бы
    пообещать приёмнику то, чего в файле нет.
    """
    assert Grid.uniform(35.0, 10.0).bounds == (0.0, 10.0, 20.0)
    short = Grid.uniform(4.0, 10.0)
    assert short.bounds == (0.0,) and short.duration == 4.0 and short.span(0) == 4.0
    assert Grid.uniform(-5.0, 10.0).duration == 0.0


def test_the_default_step_is_the_agreed_one() -> None:
    assert Grid.uniform(100.0).bounds[1] == HLS_SEGMENT_SECONDS


def test_each_segment_occupies_the_span_between_its_boundaries() -> None:
    """``k`` занимает ``[bounds[k], bounds[k+1])`` всегда, а последний - до конца фильма."""
    grid = Grid.uniform(60.0, 8.0)
    assert grid.count == 7
    assert (grid.start(2), grid.end(2), grid.span(2)) == (16.0, 24.0, 8.0)
    assert grid.end(6) == 60.0 and grid.span(6) == 12.0
    assert grid.start(-3) == 0.0 and grid.start(99) == 48.0, "за краями сетки её края"


def test_a_second_of_the_film_finds_its_own_segment() -> None:
    grid = Grid.uniform(60.0, 8.0)
    assert grid.slot_at(0.0) == 0 and grid.slot_at(-9.0) == 0
    assert grid.slot_at(8.0) == 1 and grid.slot_at(15.99) == 1
    assert grid.slot_at(500.0) == 6


def test_the_jump_over_a_bad_piece_lands_behind_it() -> None:
    """Прыжок короче сегмента приземляется в него же и перешагнуть его не может никогда.

    Сегменты разной длины (6.0-14.9 с на живом релизе), поэтому шаг тут и не может быть
    числом - только границей сетки.
    """
    grid = Grid.on_keyframes([0.0, 6.0, 21.0, 30.0, 45.0], 60.0, 10.0)
    for second in (0.0, 3.0, 5.9):
        assert grid.after(second) == grid.end(grid.slot_at(second)) > second


def test_the_manifest_promises_exactly_what_the_grid_cuts() -> None:
    """Длительность манифеста - сумма ``EXTINF``, то есть ровно длина фильма.

    Границы у манифеста и у команды ffmpeg одни и те же, поэтому обещанное приёмнику
    место фильма и есть то, что лежит в куске под этим именем.
    """
    grid = Grid.uniform(60.0, 8.0)
    lines = grid.manifest().splitlines()

    spans = [float(line[len("#EXTINF:") :].rstrip(",")) for line in lines if line[:8] == "#EXTINF:"]
    assert spans == [grid.span(k) for k in range(grid.count)]
    assert sum(spans) == pytest.approx(grid.duration), "манифест обещает не длину фильма"
    assert [line for line in lines if line.endswith(".ts")] == [
        f"v{k}.ts" for k in range(grid.count)
    ]


def test_a_grid_on_keyframes_promises_independent_segments() -> None:
    """Не украшение: каждый сегмент начинается с опорного кадра, и на этом держится перемотка."""
    grid = Grid.on_keyframes([0.0, 9.0, 21.0, 30.0, 45.0], 60.0, 10.0)
    assert grid.on_keys is True
    assert "#EXT-X-INDEPENDENT-SEGMENTS" in grid.manifest()
    assert all(place in (0.0, 9.0, 21.0, 30.0, 45.0) for place in grid.bounds)


def test_the_target_duration_is_the_longest_piece_rounded_up() -> None:
    """``EXT-X-TARGETDURATION`` меньше самого длинного куска - и приёмник бракует манифест."""
    grid = Grid.on_keyframes([0.0, 9.0, 21.0, 30.0, 45.0], 60.0, 10.0)
    assert grid.target() == math.ceil(max(grid.span(k) for k in range(grid.count)))
    assert grid.target() >= 1


def test_a_piece_is_born_below_the_ceiling_and_not_exactly_at_it() -> None:
    """Сетка целится ниже потолка: вес куска у неё предсказан, а не известен.

    Замер по 84 сохранённым картам опорных кадров: у 0.75 % кусков предсказанный вес
    стоит в пределах процента под потолком, и промах предсказателя решает их судьбу за
    содержимое. Обещанный ровно в потолок кусок рождается за ним и уходит во второй
    прогон ffmpeg над тем же местом.
    """
    keys = [round(k * 0.5, 3) for k in range(41)]
    sizes = [int(place * 2.0e6) for place in keys]  # 2 МБ в секунду
    cap = 8.0e6
    grid = Grid.on_keyframes(keys, 20.0, 10.0, sizes=sizes, cap=cap)
    assert grid.weigh is not None

    body = range(grid.count - 1)  # хвост потолком веса не судится никогда
    heaviest = max(grid.weigh(grid.start(k), grid.end(k)) for k in body)
    assert heaviest <= cap * (1.0 - GRID_WEIGHT_MARGIN), (
        f"кусок обещан в {heaviest:.0f} байт при потолке {cap:.0f} - это рождение за потолком"
    )
    assert max(grid.span(k) for k in body) < 10.0, "потолок веса не укоротил ни одного куска"
