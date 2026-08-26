"""Зеркало :mod:`torrcast.domain.keys_tail_gaps`: порог хвоста карты стоит в пустом промежутке.

Сторожит тут не само число, а замер, из-за которого оно такое: порог обязан лежать ВЫШЕ
самой большой доли здоровой карты и НИЖЕ самой маленькой доли битой - то есть в
промежутке, где нет ни одной карты корпуса.
"""

from __future__ import annotations

from torrcast.domain.keys_tail_gaps import KEYS_TAIL_GAPS

#: Самая большая доля «хвост / самая широкая дыра» среди здоровых карт корпуса (141 карта
#: живой полки владельца, 137 здоровых).
HEALTHY_MOST = 2.33

#: Самая маленькая доля среди тех четырёх, у которых индекс кончился раньше фильма:
#: 28.25, 28.70, 43.46 и 316.76.
BROKEN_LEAST = 28.25


def test_the_threshold_stands_in_the_empty_gap_of_the_corpus() -> None:
    """Между 2.33 и 28.25 нет ни одной карты корпуса - порог обязан лежать внутри."""
    assert HEALTHY_MOST < KEYS_TAIL_GAPS < BROKEN_LEAST


def test_the_threshold_is_a_multiple_and_not_a_number_of_seconds() -> None:
    """Мерка своя у каждой карты: «один GOP» у GOP 1.3 с и у GOP 10.4 с - разные секунды.

    Порог, выраженный секундами, на карте с GOP 10.4 с отвергал бы здоровый хвост, а на
    карте с GOP 1.3 с пропускал бы кусок в сотни секунд.
    """
    assert 1.0 < KEYS_TAIL_GAPS < 10.0, "доля от дыры карты, а не секунды"
    for widest, tail in ((1.3, 396.6), (9.9, 283.7), (2.0, 87.0), (2.0, 56.6)):
        assert tail > widest * KEYS_TAIL_GAPS, f"битая карта прошла: дыра {widest}, хвост {tail}"
    for widest, tail in ((10.4, 24.3), (10.0, 16.6), (5.0, 6.3), (2.0, 2.0)):
        assert tail <= widest * KEYS_TAIL_GAPS, f"здоровая карта отвергнута: {widest}, {tail}"
