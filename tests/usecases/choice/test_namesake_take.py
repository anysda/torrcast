"""Зеркало :mod:`torrcast.usecases.choice.namesake_take`: самая живая тёзка дефолта.

🔴 TC-812, решение владельца 26-08-2026: тёзки по году - разные картины под одним
именем - больше не спрашивают: берётся самая живая, и берётся не молча. Франшизу это
не трогает: дефолт номерованных частей - по-прежнему первая живая часть.
"""

from __future__ import annotations

from tests.usecases.choice.world import Outside, outside, parts, plan
from torrcast.domain.facts.map_picture import MapPicture
from torrcast.usecases.choice.enter_take import enter_take
from torrcast.usecases.choice.namesake_take import namesake_take
from torrcast.usecases.discover._search_state import _configure_known


def test_the_liveliest_namesake_is_taken() -> None:
    """«мумия»: первая живая по хронологии - 1999 год, а живее всех тёзка 2017 года."""
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))

    with outside(Outside()):
        assert namesake_take(mummy) == 2


def test_the_default_itself_is_taken_when_it_is_the_liveliest() -> None:
    """«титаник»: живее всех сам дефолт - взятие перестало быть вопросом, не сменившись."""
    titanic = parts(("Титаник", 1943, 1), ("Титаник", 1953, 2), ("Титаник", 1997, 165))

    with outside(Outside()):
        assert namesake_take(titanic) == 3


def test_a_dead_namesake_is_not_taken_however_early_it_stands() -> None:
    """Мёртвая тёзка весит свой рой, и живой соседке она не конкурент."""
    mummy = parts(("Мумия", 1932, 2), ("Мумия", 1999, 47))

    with outside(Outside()):
        assert namesake_take(mummy) == 2


def test_without_namesakes_there_is_no_take() -> None:
    """Разные названия - не тёзки: у частей франшизы своё правило, у соседей - свой страж."""
    cars = [
        plan("Тачки", 2006, part=1, seeders=66),
        plan("Тачки 2", 2011, part=2, seeders=71),
        plan("Тачки 3", 2017, part=3, seeders=121),
    ]

    with outside(Outside()):
        assert namesake_take(cars) == 0


def test_a_differently_named_livelier_neighbour_is_not_taken() -> None:
    """Живее всех в меню - картина с ДРУГИМ именем: она в круг взятия не входит вовсе."""
    menu = parts(("Моана", 2016, 40), ("Моана 2", 2024, 222))

    with outside(Outside()):
        assert namesake_take(menu) == 0


def test_a_single_picture_has_no_namesakes() -> None:
    """Картина одна - тёзок нет, и вопроса о круге взятия нет."""
    with outside(Outside()):
        assert namesake_take(parts(("Мумия", 1999, 47))) == 0


def test_namesakes_of_the_other_kind_are_out_of_the_take() -> None:
    """Спросили серию - одноимённая полнометражка не «вариант поживее», а другое кино."""
    vikings = [
        plan("Викинги", 1958, seeders=300, asked_series=True),
        plan("Викинги", 2013, kind="tv", seeders=90, asked_series=True),
    ]

    with outside(Outside()):
        assert namesake_take(vikings) == 0, "тёзки считаются внутри названного типа"


def test_the_namesake_of_the_year_named_is_taken() -> None:
    """TC-1398: «Призрак в доспехах 2026» - год назван, и живой фильм 1995 года не подмена ему."""
    ghost = [
        plan("Призрак в доспехах", 1995, seeders=300),
        plan("Призрак в доспехах", 2026, kind="tv", seeders=60),
    ]

    with outside(Outside()):
        assert namesake_take(ghost) == 1
        assert namesake_take(ghost, "Призрак в доспехах 2026") == 2
        assert namesake_take(ghost, "Призрак в доспехах 2031") == 1


def test_enter_takes_the_namesake_of_the_year_named() -> None:
    """Enter спрашивает взятие тёзки тем же запросом: «Мумия 2017» не уезжает в 1999 год."""
    mummy = parts(("Мумия", 1999, 300), ("Мумия", 2017, 58))

    with outside(Outside()):
        assert enter_take(mummy, "Мумия").number == 1
        assert enter_take(mummy, "Мумия 2017").number == 2


def test_a_dead_namesake_of_the_year_named_leaves_the_liveliest() -> None:
    """Год назван, но играть картине этого года нечем: берётся самая живая, как прежде."""
    ghost = [
        plan("Призрак в доспехах", 1995, seeders=300),
        plan("Призрак в доспехах", 2026, kind="tv", seeders=1),
    ]

    with outside(Outside()):
        assert namesake_take(ghost, "Призрак в доспехах 2026") == 1


def _map(*rows: tuple[str, int, str, int], series: bool = False) -> None:
    """Офлайн-карта IMDb: «прокатное имя, год, оригинал, голоса» на каждую картину."""
    known = [
        MapPicture(name, year, series, original, votes) for name, year, original, votes in rows
    ]
    _configure_known(lambda title: [row for row in known if row.name == title])


def test_a_lively_namesake_of_another_work_does_not_replace_the_known_one() -> None:
    """«сталкер»: рой триллера 2023 года под тем же именем живее, но работа известна 1979-я."""
    stalker = parts(("Сталкер", 1979, 177), ("Сталкер", 2023, 1317))
    _map(("Сталкер", 1979, "Stalker", 158000), ("Сталкер", 2023, "Strange Darling", 72800))

    with outside(Outside()):
        assert namesake_take(stalker, "сталкер") == 1


def test_the_new_work_wins_when_the_map_knows_it_better() -> None:
    """«блеф»: 2026-я известнее и живее итальянского фильма 1976 года."""
    bluff = parts(("Блеф", 1976, 51), ("Блеф", 2026, 958))
    _map(("Блеф", 1976, "Bluff storia di truffe", 5265), ("Блеф", 2026, "The Bluff", 19935))

    with outside(Outside()):
        assert namesake_take(bluff, "блеф") == 2


def test_a_remake_of_the_same_work_is_taken_by_its_swarm() -> None:
    """«как приручить дракона»: оригинал один, 2010-я известнее, но берут живую 2025-ю."""
    dragon = parts(("Как приручить дракона", 2010, 352), ("Как приручить дракона", 2025, 2969))
    _map(
        ("Как приручить дракона", 2010, "How to Train Your Dragon", 911000),
        ("Как приручить дракона", 2025, "How to Train Your Dragon", 142000),
    )

    with outside(Outside()):
        assert namesake_take(dragon, "как приручить дракона") == 2


def test_a_namesake_the_map_does_not_know_gives_way_to_a_proven_one() -> None:
    """«брат»: свежий рой 2025 года живее, но карта доказывает только 1997-й."""
    brother = parts(("Брат", 1997, 5), ("Брат", 2025, 7))
    _map(("Брат", 1997, "Brat", 29560))

    with outside(Outside()):
        assert namesake_take(brother, "брат") == 1
        assert namesake_take(brother, "брат 2025") == 2, "год, названный запросом, решает"
