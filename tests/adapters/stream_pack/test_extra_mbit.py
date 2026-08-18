"""Зеркало :mod:`torrcast.adapters.stream_pack.extra_mbit`: поправка «контейнер → ТВ».

Десять озвучек и восемь субтитров в контейнере на ТВ не уезжают, и потолок веса куска
обязан знать об этом до первого куска, а не после калибровки перекода.
"""

from __future__ import annotations

import pytest

from torrcast.adapters.stream_pack.extra_mbit import extra_mbit
from torrcast.domain.film_keys import FilmKeys

#: Ровный GOP в две секунды на минуту фильма и ровный битрейт 2 МБ/с.
KEYS = FilmKeys(
    60.0, [round(k * 2.0, 3) for k in range(31)], [k * (2 << 20) for k in range(31)], "mkv"
)


def test_what_does_not_travel_to_the_tv_is_measured_from_the_map_and_the_passport() -> None:
    """Ровно то же число, что набирает калибровка по факту, но известное до первого куска.

    Паспорт молчит - ноль: потолок тогда считает по контейнеру целиком, то есть режет с
    запасом. Запас безопасен, недооценка нет.
    """
    assert extra_mbit(KEYS, 0.0) == 0.0
    container = (KEYS.offset[-1] - KEYS.offset[0]) * 8 / (KEYS.at[-1] - KEYS.at[0]) / 1e6
    assert extra_mbit(KEYS, 8.0) == pytest.approx(container - 8.0)
    assert container == pytest.approx(8.389, abs=0.001)
    assert extra_mbit(KEYS, 1e9) == 0.0, "паспорт тяжелее контейнера - вычитать нечего"
    assert extra_mbit(FilmKeys(60.0, [0.0, 2.0], [], "mkv"), 8.0) == 0.0
