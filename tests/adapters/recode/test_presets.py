"""Таблица пресетов: порядок от лучшего качества к быстрейшему и замеренные скорости."""

from __future__ import annotations

from torrcast.adapters.recode.presets import PRESETS


def test_the_table_goes_from_the_best_picture_to_the_fastest() -> None:
    """Порядок таблицы - это правило выбора: первый годный пресет и есть самый качественный.

    Перепутай порядок - и выбор пресета начнёт брать ``ultrafast`` там, где успевал
    ``veryfast``, то есть отдаст чёткость даром.
    """
    names = [name for name, _speed in PRESETS]
    speeds = [speed for _name, speed in PRESETS]

    assert names == ["veryfast", "superfast", "ultrafast"]
    assert speeds == sorted(speeds), "скорость обязана расти слева направо"
    assert speeds[-1] == max(speeds), "самый быстрый - последний, к нему и падают при отказе"


def test_the_speeds_are_the_measured_ones_scaled_down_by_a_tenth() -> None:
    """Числа замерены на 4 vCPU и занижены примерно на 10 %: рядом работают соседи.

    Замер: ultrafast 4.36x, superfast 2.62x, veryfast 1.54x.
    """
    assert PRESETS == (("veryfast", 1.40), ("superfast", 2.35), ("ultrafast", 3.90))
    for (_name, speed), measured in zip(PRESETS, (1.54, 2.62, 4.36), strict=True):
        assert 0.85 <= speed / measured <= 0.95, "занижено примерно на десятую, а не на глаз"
