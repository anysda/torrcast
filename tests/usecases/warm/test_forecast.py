"""Предсказание веса участка: по нашему битрейту при перекоде и по карте при копии."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import pytest

import torrcast.usecases.warm._state as _state
from tests.usecases.warm.world import grid, warmer
from torrcast.domain.profile import ANDROID_TV, CAUTIOUS
from torrcast.usecases.warm.forecast import _forecast

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class _Encode:
    mbit: float = 8.0


def test_a_recoded_run_is_measured_by_our_own_bitrate(tmp_path: Path) -> None:
    """Перекодируем мы - значит и вес считаем по своему битрейту, а не по контейнеру."""
    warm = warmer(tmp_path, encode=_Encode())
    seconds = sum(warm.grid.span(s) for s in range(warm.grid.count))
    want = (8.0 + _state.AUDIO_MBIT) * _state.TS_OVERHEAD * seconds * 1e6 / 8

    assert _forecast(warm, 0, warm.grid.count - 1) == pytest.approx(want)


def test_a_copy_is_weighed_piece_by_piece_by_the_keyframe_map(tmp_path: Path) -> None:
    """Копия взвешивается той же картой, по которой сетка ставила границы."""
    weighed = replace(grid(), weigh=lambda a, b: (b - a) * 1000.0)
    warm = warmer(tmp_path, grid=weighed)

    assert _forecast(warm, 0, 1) == pytest.approx(20_000.0), "карта посчитала не свои куски"
    assert _forecast(warm, 0, warm.grid.count - 1) == pytest.approx(60_000.0)


def test_without_a_map_or_a_passport_the_ceiling_of_that_receiver_answers(tmp_path: Path) -> None:
    """Ни карты, ни паспорта - вес куска оценить нечем, и просим по потолку ТОГО
    приёмника, для которого греем, а не по осторожному умолчанию завода.

    Замер на релизах, у которых карта опорных кадров отвергнута, а сетка выходит ровная:
    прогноз просил одно и то же на любом приёмнике - на 42.85 % меньше, чем нужно
    приёмнику с потолком 28 МБ. Места по такому расчёту хватало всегда, а на диск ложилось
    меньше обещанного.
    """
    warm = warmer(tmp_path, cap=ANDROID_TV.max_segment_bytes)
    assert warm.grid.weigh is None, "ровная сетка не должна нести предсказателя веса"
    assert ANDROID_TV.max_segment_bytes != CAUTIOUS.max_segment_bytes, "потолки сравнялись"

    assert _forecast(warm, 0, warm.grid.count - 1) == pytest.approx(
        warm.grid.count * ANDROID_TV.max_segment_bytes
    )


def test_without_a_map_an_unknown_receiver_still_gets_the_cautious_ceiling(
    tmp_path: Path,
) -> None:
    """Отрицательная проба: не названный потолок остаётся осторожным, а не любым.

    Осторожные 16 МБ завоёваны на телевизоре, и запасная ветка обязана оставлять их тому,
    про чей потолок ничего не известно. Проба падает и в другую сторону: отними правка
    осторожное умолчание - и незнакомому приёмнику досталось бы чужое число.
    """
    warm = warmer(tmp_path)
    assert warm.cap == CAUTIOUS.max_segment_bytes, "умолчание прогрева перестало быть осторожным"

    assert _forecast(warm, 0, warm.grid.count - 1) == pytest.approx(
        warm.grid.count * CAUTIOUS.max_segment_bytes
    )


#: Средний вес фильма по паспорту, Мбит/с: столько уезжает на ТВ у релиза, на котором
#: мерили запасную ветку. Число выбрано так, чтобы кусок вышел МЕЖДУ двумя потолками -
#: осторожным и потолком приставки: ровно там и лежат настоящие куски, и ровно этого
#: обе потолочные прикидки не видели.
BETWEEN_MBIT = 15.5


def test_without_a_map_the_passport_weighs_the_pieces(tmp_path: Path) -> None:
    """Карты нет, но паспорт знает средний вес фильма - по нему и просим.

    Потолок - это верхняя ГРАНИЦА куска, а не его вес, и оценкой веса он промахивается в
    обе стороны: осторожные 16 МБ занижают, потолок приставки 28 МБ завышает. Настоящие
    куски лежат между ними - там, куда и показывает паспорт.
    """
    warm = warmer(tmp_path, cap=ANDROID_TV.max_segment_bytes, delivered=BETWEEN_MBIT)
    assert warm.grid.weigh is None, "ровная сетка не должна нести предсказателя веса"
    piece = BETWEEN_MBIT * 10.0 * 1e6 / 8

    assert _forecast(warm, 0, warm.grid.count - 1) == pytest.approx(warm.grid.count * piece)
    assert CAUTIOUS.max_segment_bytes < piece < ANDROID_TV.max_segment_bytes, (
        "проба перестала мерить то, ради чего заведена: кусок обязан лежать между потолками"
    )


def test_the_receiver_ceiling_stays_an_upper_bound_over_the_passport(tmp_path: Path) -> None:
    """Отрицательная проба: паспорт не отменяет потолок, а зажимается им сверху.

    Кусок тяжелее потолка показ с диска не возьмёт, и просить на него больше потолка
    незачем. Убери зажим - и на тяжёлом релизе без карты прогноз попросит у бюджета
    больше, чем показу вообще пригодится.
    """
    warm = warmer(tmp_path, cap=CAUTIOUS.max_segment_bytes, delivered=100.0)
    by_passport = 100.0 * 10.0 * 1e6 / 8
    assert CAUTIOUS.max_segment_bytes < by_passport, "паспорт обязан перебивать потолок"

    assert _forecast(warm, 0, warm.grid.count - 1) == pytest.approx(
        warm.grid.count * CAUTIOUS.max_segment_bytes
    )
