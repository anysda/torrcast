"""Зеркало :mod:`torrcast.usecases.choice.namesake_line`: строка взятия живейшей тёзки.

Подмена перестала быть молчаливой - значит строка обязана назвать взятую картину
годом, сказать, сколько под этим именем есть ещё, и назвать ключ ``--menu``.
"""

from __future__ import annotations

from tests.usecases.choice.world import Outside, outside, parts
from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.choice.namesake_line import namesake_line


def test_the_line_names_the_taken_picture_the_rest_count_and_the_menu_key() -> None:
    """«мумия»: взятая названа с годом, остальные - числом, ход к ним - за ``--menu``."""
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))

    with outside(Outside()):
        assert namesake_line(mummy, 2, "мумия") == phrase(
            "choice.namesake_taken",
            picture="Мумия (2017)",
            seeds=58,
            others=1,
            asked="мумия",
        )


def test_the_liveliness_is_named_by_its_seed_count() -> None:
    """«Самая живая» без числа была бы просьбой поверить на слово - число названо."""
    titanic = parts(("Титаник", 1943, 1), ("Титаник", 1953, 2), ("Титаник", 1997, 165))

    with outside(Outside()):
        line = namesake_line(titanic, 3, "титаник")

    assert line == phrase(
        "choice.namesake_taken",
        picture="Титаник (1997)",
        seeds=165,
        others=2,
        asked="титаник",
    )


def test_only_the_namesakes_are_counted_not_the_whole_menu() -> None:
    """Соседи с другим именем - не «другие картины под этим именем», и в счёт не идут."""
    menu = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58), ("Мумия возвращается", 2001, 90))

    with outside(Outside()):
        line = namesake_line(menu, 2, "мумия")

    assert line == phrase(
        "choice.namesake_taken",
        picture="Мумия (2017)",
        seeds=58,
        others=1,
        asked="мумия",
    ), "«Мумия возвращается» - не тёзка"
