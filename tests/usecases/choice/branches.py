"""Таблица веток взятия: по одному живому меню на каждое правило ступени взятия.

Отдельным файлом, а не фикстурой внутри зеркала: по этим же меню ходят два разных
зеркала - и сама ступень взятия (:mod:`tests.usecases.choice.test_enter_take`), и шов
прогрева на боевом пути (:mod:`tests.usecases.cast_command.test_warm_matches_enter`).
Разведи их по двум редакциям меню - и шов проверялся бы не на тех входах, на которых
проверялась ступень.

🔴 Таблица обязана покрывать все ветки :func:`~torrcast.usecases.choice.enter_take.enter_take`
целиком: именно это и делает шов непроходимым для нового правила. Имена веток зеркало шва
вычитывает из исходника самой ступени, так что правило, под которое тут нет меню, роняет
зеркало, а не проезжает молча.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from tests.usecases.choice.world import film, parts, plan
from torrcast.usecases.select.plan import Plan

#: Раздача «Тачек» на кассете: кодек и качество не проходят ворота отбора, и играть
#: первой части нечем - на ней и стоит страж первой части.
VHS = film("Cars 2006 DVDRip XviD", seeders=100, codec="XviD", quality=None)


@dataclass(frozen=True, slots=True)
class Branch:
    """Одно меню, один запрос и одно правило взятия, которое на них срабатывает."""

    #: Имя правила: ровно то, что ступень кладёт в :attr:`Take.why`.
    why: str
    #: Как собрать меню. Функцией, а не готовым списком: планы по дороге правятся
    #: (:meth:`Bench.reorder`), и одна редакция на все зеркала протекала бы между ними.
    menu: Callable[[], list[Plan]]
    asked: str
    pick: int | None = None
    #: Флаг ``--menu``: список поднимается там, где о выборе сказать нечего.
    flag: bool = False
    #: Номер, который называет человек за явным ``--menu``.
    answer: int | None = None
    #: Номер картины меню, которую по этой ветке включит Enter; 0 - взятия нет.
    takes: int = 0


def _mummy() -> list[Plan]:
    """Три тёзки по году: живее всех самая свежая, а первой в списке стоит старейшая."""
    return parts(("Мумия", 1999, 47), ("Мумия", 2017, 58), ("Мумия", 2026, 300))


def _ice() -> list[Plan]:
    """Одна найденная картина, и это ЧУЖАЯ часть франшизы: спрашивали не её."""
    return [plan("Лёд 3", 2024, part=3, seeders=3)]


def _cars() -> list[Plan]:
    """Франшиза, у которой живы все части: о выборе сказать нечего."""
    return [
        plan("Тачки", 2006, part=1, seeders=66),
        plan("Тачки 2", 2011, part=2, seeders=71),
        plan("Тачки 3", 2017, part=3, seeders=121),
    ]


def _cars_on_tape() -> list[Plan]:
    """Та же франшиза, но первой части играть нечем: дефолт подменил бы её другой."""
    return [
        plan("Тачки", 2006, part=1, pool=[VHS]),
        plan("Тачки 2", 2011, part=2, seeders=40),
        plan("Тачки 3", 2017, part=3, seeders=121),
    ]


def _cars_without_the_first() -> list[Plan]:
    """Спрошенной первой части в выдаче нет вовсе: выбирать между «той» и «другой» нечего."""
    return [
        plan("Тачки 2", 2011, part=2, seeders=40),
        plan("Тачки 3", 2017, part=3, seeders=121),
    ]


def _bleach() -> list[Plan]:
    """Имя названо целиком, а живее - продолжение с другим именем."""
    return [
        plan("Блич", 2004, kind="tv", seeders=3, asked_series=True),
        plan("Блич: Тысячелетняя кровавая война", 2022, kind="tv", seeders=40, asked_series=True),
    ]


def _master() -> list[Plan]:
    """Одно имя, два вида: живее полный метр, а сериал под тем же именем стоит ниже."""
    return [
        plan("Мастер и Маргарита", 2024, seeders=300),
        plan("Мастер и Маргарита", 2005, kind="tv", seeders=40),
    ]


def _moana() -> list[Plan]:
    """Верх меню - мёртвая документалка с другим именем: о выборе есть что сказать."""
    return parts(
        ("Моана: романтика золотого века", 1926, 1), ("Моана", 2016, 222), ("Моана 2", 2024, 140)
    )


def branches() -> list[Branch]:
    """Все ветки взятия по одной, в порядке, в котором их перебирает сама ступень."""
    return [
        Branch("номер флагом", _mummy, "мумия", pick=2, takes=2),
        Branch("чужая часть, взята первая живая", _ice, "лёд", takes=1),
        Branch("картина одна", _ice, "лёд 3", takes=1),
        Branch("дефолт без вопроса", _cars, "тачки", takes=1),
        Branch("спрошенной части нет", _cars_without_the_first, "тачки", takes=1),
        Branch("имя названо целиком", _bleach, "блич", takes=2),
        Branch("сериал под одним именем с фильмом", _master, "мастер и маргарита", takes=2),
        Branch("тёзки по году", _mummy, "мумия", takes=3),
        Branch("страж первой части, взята первая живая", _cars_on_tape, "тачки", takes=2),
        Branch("страж первой части", _cars_on_tape, "тачки", flag=True, answer=3),
        Branch("имя названо, дефолт мимо", _bleach, "блич", flag=True, answer=2),
        Branch("взята первая живая", _moana, "моана", takes=2),
        Branch("дефолт с вопросом", _moana, "моана", flag=True, takes=2),
    ]
