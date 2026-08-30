"""Зеркало :mod:`torrcast.usecases.choice.warm_order`: кого греть под меню.

Прогрев под меню занимает раздачи, полосу и место в TorrServer, и достаётся он голове
списка. Первой в этой голове стоит та картина, в которую попадёт Enter, а дальше идёт
порядок, который видит человек: он хронологический, и переставлять его под живость
нельзя - грелось бы не то, что нажмут.

🔴 TC-829. Своего мнения о том, кого возьмёт Enter, у прогрева нет: номер приезжает
готовым приговором от той ступени, которая картину и возьмёт. Ровно это тут и мерится.
"""

from __future__ import annotations

from tests.usecases.choice.world import parts
from torrcast.usecases.choice.enter_take import enter_take
from torrcast.usecases.choice.take import Take
from torrcast.usecases.choice.warm_order import warm_order


def test_the_mummy_is_warmed_by_the_year_that_enter_will_start() -> None:
    """🔴 Поимённо про «мумию»: греется 2026-я, потому что её же включит Enter.

    Три тёзки по году, и живее всех самая свежая: ступень взятия берёт её
    (:func:`namesake_take`), а прогрев целился в первую живую по списку - в 1999-ю. Зритель
    жал Enter, получал 2026-ю и ждал подъёма её роя с нуля, пока прогретая 1999-я стояла
    в TorrServer никому не нужная. Спрошено это теперь ОДИН раз и одной ступенью.
    """
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58), ("Мумия", 2026, 300))

    take = enter_take(mummy, "мумия")

    assert take.number == 3, "Enter включает самую живую из тёзок"
    assert [warmed.picture.year for warmed in warm_order(mummy, take)] == [2026, 1999, 2017]


def test_the_warmup_has_no_opinion_of_its_own_about_who_enter_takes() -> None:
    """🔴 Прогрев не пересчитывает дефолт, а читает приговор - и это главное его свойство.

    Первая живая картина тут первая же по списку, и посчитай прогрев сам - он взял бы её.
    Приговор называет третью, и греется третья: другого мнения у этой единицы нет
    физически, а значит и разойтись со взятием нечем.
    """
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58), ("Мумия", 2026, 300))

    assert [warmed.picture.year for warmed in warm_order(mummy, Take(3))] == [2026, 1999, 2017]


def test_the_rest_of_the_queue_keeps_the_order_the_person_sees() -> None:
    """Хвост очереди хронологический, а не по живости: человек тычет в соседний номер.

    Отсортируй хвост по сидам - и после дефолта грелась бы 2017-я с её 58 сидами, а не
    та 1999-я, что стоит в списке первой у человека перед глазами.
    """
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58), ("Мумия", 2026, 300))

    assert [warmed.picture.year for warmed in warm_order(mummy, Take(3))][1:] == [1999, 2017]


def test_no_picture_is_dropped_from_the_warmup_queue() -> None:
    """Список отдаётся целиком: решать, кого греть, а кого нет, эта единица не берётся."""
    cars = parts(("Тачки", 2006, 66), ("Мультачки", 2008, 0), ("Тачки 2", 2011, 1))

    assert warm_order(cars, Take(1)) == cars
