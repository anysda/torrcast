"""Зеркало :mod:`torrcast.usecases.choice.warm_order`: кого греть под меню.

Прогрев под меню занимает раздачи, полосу и место в TorrServer, и достаётся он голове
списка. Первой в этой голове стоит та картина, в которую попадёт Enter, а дальше идёт
порядок, который видит человек: он хронологический, и переставлять его под живость
нельзя - грелось бы не то, что нажмут.
"""

from __future__ import annotations

from tests.usecases.choice.world import parts
from torrcast.usecases.choice.warm_order import warm_order


def test_the_warmup_follows_the_order_the_person_sees_and_not_the_liveliness() -> None:
    """Греется голова списка, а не верх ранжира: порядок меню остаётся хронологическим.

    Отсортируй прогрев по сидам - и на «мумии» грелась бы часть 2026 года с сотнями
    сидов, пока человек жмёт Enter на «Мумии» 1999 года.
    """
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58), ("Мумия", 2026, 300))

    assert [warmed.picture.year for warmed in warm_order(mummy)] == [1999, 2017, 2026]


def test_the_picture_enter_will_start_is_warmed_first_even_from_the_middle_of_the_list() -> None:
    """🔴 Первой греется картина, в которую попадёт Enter, где бы она ни стояла в списке.

    Греется голова этого списка, а дефолт стоит шестым у «медведь s2e7» и девятым у
    «блич s1e1» - то есть за нею. Оставь порядок списка, и человек, нажавший Enter,
    ждал бы подъёма роя с нуля ровно там, где прогрев для того и заведён.
    """
    titanic = parts(("Титаник", 1943, 1), ("Титаник", 1953, 2), ("Титаник", 1997, 165))

    assert [warmed.picture.year for warmed in warm_order(titanic)] == [1997, 1943, 1953]


def test_no_picture_is_dropped_from_the_warmup_queue() -> None:
    """Список отдаётся целиком: решать, кого греть, а кого нет, эта единица не берётся."""
    cars = parts(("Тачки", 2006, 66), ("Мультачки", 2008, 0), ("Тачки 2", 2011, 1))

    assert warm_order(cars) == cars
