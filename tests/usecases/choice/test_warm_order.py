"""Зеркало :mod:`torrcast.usecases.choice.warm_order`: кого греть под меню.

Прогрев под меню занимает раздачи, полосу и место в TorrServer, и достаётся он голове
списка. Голова тут - та, что видит человек, а не та, что живее: список хронологический,
и переставь его прогрев под себя - грелось бы не то, что нажмут.
"""

from __future__ import annotations

from tests.usecases.choice.world import parts
from torrcast.usecases.choice import warm_order


def test_the_warmup_follows_the_order_the_person_sees_and_not_the_liveliness() -> None:
    """Греется голова списка, а не верх ранжира: порядок меню остаётся хронологическим.

    Отсортируй прогрев по сидам - и на «мумии» грелась бы часть 2026 года с сотнями
    сидов, пока человек жмёт Enter на «Мумии» 1999 года.
    """
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58), ("Мумия", 2026, 300))

    assert [warmed.picture.year for warmed in warm_order(mummy)] == [1999, 2017, 2026]


def test_no_picture_is_dropped_from_the_warmup_queue() -> None:
    """Список отдаётся целиком: решать, кого греть, а кого нет, эта единица не берётся."""
    cars = parts(("Тачки", 2006, 66), ("Мультачки", 2008, 0), ("Тачки 2", 2011, 1))

    assert warm_order(cars) == cars
