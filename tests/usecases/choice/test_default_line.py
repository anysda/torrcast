"""Зеркало :mod:`torrcast.usecases.choice.default_line`: что случится по Enter.

🔴 TC-204. Порядок меню хронологический, а дефолт - первая ЖИВАЯ картина, и совпадают
они меньше чем в половине меню: в замере 45 многокартинных меню из 82, а у «ван пис
s1e1» дефолт стоял строкой 33 из 35. Одной цифры в скобках человеку мало - он видит
номер, а не название.
"""

from __future__ import annotations

from tests.usecases.choice.world import parts
from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.choice.default_line import default_line


def test_the_default_is_named_out_loud_and_not_left_as_a_bare_number() -> None:
    """Строка называет картину именем и годом, а не одной цифрой.

    Потеряй она имя - человек читал бы «пункт 2 из 3» и всё равно лез бы глазами вверх
    по тридцати пяти строкам, ради чего строка и заведена.
    """
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58), ("Мумия", 2026, 300))

    assert default_line(mummy, 2) == phrase(
        "choice.default", picture="Мумия (2017)", number=2, total=3
    )


def test_the_line_counts_the_whole_menu_so_the_number_has_something_to_mean() -> None:
    """Номер назван вместе с длиной списка: «пункт 33 из 35» и есть его смысл."""
    long_menu = parts(*[(f"Ван Пис {number}", 2000 + number, 10) for number in range(1, 36)])

    assert default_line(long_menu, 33) == phrase(
        "choice.default", picture="Ван Пис 33 (2033)", number=33, total=35
    )
