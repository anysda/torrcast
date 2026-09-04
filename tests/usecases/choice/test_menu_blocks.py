"""Зеркало :mod:`torrcast.usecases.choice.menu_blocks`: меню франшизы кусками.

Формат такой, а не таблицей, ровно из-за узкого терминала: название бывает длинным
(«Тачки: Мультачки. Байки Мэтра»), а описание - тем более, и колонки разъехались бы на
первой же франшизе. Отдельная строка вместо колонки ещё и читается сверху вниз.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

import pytest

from tests.usecases.choice.world import Outside, outside, parts, plan
from torrcast.domain.catalogs.tongue import EN, RU, _choose_tongue
from torrcast.domain.facts.fact import Fact
from torrcast.domain.facts.settings import HTTP_TIMEOUT
from torrcast.domain.numbered_line import _numbered_line
from torrcast.runtime.menu_facts import MenuFacts
from torrcast.usecases.choice._named import _BLURB_INDENT
from torrcast.usecases.choice.menu_blocks import menu_blocks
from torrcast.usecases.facts import Facts
from torrcast.usecases.select.plan import Plan

#: Живое описание из Википедии: длиннее строки терминала и с дефисом внутри слова.
ABOUT = (
    "«Тачки» - американский компьютерно-анимационный фильм студии Pixar о гоночном "
    "автомобиле, который застрял в маленьком городке у трассы"
)
Blurbs = dict[tuple[str, int | None], Fact]


@pytest.fixture(autouse=True)
def _russian_catalog() -> None:
    """Русские строки меню в этом зеркале явно выбирают русский каталог."""
    _choose_tongue(RU)


def menu_rows(plans: list[Plan], facts: Facts | None = None, width: int = 0) -> list[str]:
    """Меню сплошным списком строк - тем самым, что уходит на экран."""
    return [line for block in menu_blocks(plans, facts, width) for line in block]


class Cached:
    """Кэш справки, в котором уже лежит всё, что спросят: в сеть меню не пойдёт вовсе."""

    def __init__(self, ready: Blurbs) -> None:
        self.ready = ready

    def blurbs(self, wanted: list[tuple[str, int | None]]) -> Blurbs:
        return {key: self.ready[key] for key in wanted if key in self.ready}

    def remember(self, found: Blurbs, misses: Iterable[tuple[str, int | None]] = ()) -> None:
        return None


class Offline:
    """Источник справки, до которого меню не доходит: всё найдено в кэше."""

    def fetch(
        self,
        wanted: list[tuple[str, int | None]],
        timeout: float = HTTP_TIMEOUT,
        ready: Callable[[Blurbs], None] | None = None,
        kinds: dict[tuple[str, int | None], str] | None = None,
    ) -> tuple[Blurbs, set[tuple[str, int | None]]]:
        raise AssertionError("справка уже в кэше - ходить за ней некуда")


class Ready(MenuFacts):
    """Справка меню, собранная на кэше теста: тот же класс, что зовёт живое меню."""

    def __init__(self, ready: Blurbs) -> None:
        Facts.__init__(self, list(ready), store=Cached(ready), source=Offline())


def test_every_picture_gets_its_number_starting_from_one() -> None:
    """Номер пункта - это то, чем человек отвечает на вопрос, и считается он с единицы.

    Съедь нумерация на ноль - и ответ «1» включал бы вторую картину списка.
    """
    with outside(Outside()):
        rows = menu_rows(parts(("Тачки", 2006, 66), ("Тачки 2", 2011, 40)))

    assert rows == ["  1. Тачки (2006)", "  2. Тачки 2 (2011)"]


def test_the_rating_and_the_runtime_stand_in_the_same_line_as_the_title() -> None:
    """Рейтинг и хронометраж - в строку пункта: глаз идёт по номерам, а не по колонкам."""
    world = Outside(blurb=Fact(rating="IMDb 7.1", runtime="1 ч 57 мин"))

    with outside(world):
        rows = menu_rows(parts(("Тачки", 2006, 66)))

    assert rows == ["  1. Тачки (2006) · IMDb 7.1 · 1 ч 57 мин"]


def test_a_description_is_wrapped_by_words_and_never_cut_to_the_width() -> None:
    """Описание занимает столько строк, сколько нужно фразе, и доезжает целиком.

    Раньше оно резалось по ширине терминала, и в меню оставался огрызок «американский
    компьютерно-анимационный…»: ни жанра, ни года, ни возможности дочитать. Место
    экономить тут не на чем - вопрос задаётся один раз.
    """
    with outside(Outside(blurb=Fact(about=ABOUT), width=60)):
        rows = menu_rows(parts(("Тачки", 2006, 66)))

    assert len(rows) > 2, "фраза длиннее строки терминала и переносится, а не режется"
    assert all(row.startswith(_BLURB_INDENT) for row in rows[1:])
    assert " ".join(row.strip() for row in rows[1:]) == ABOUT


def test_a_hyphen_inside_a_word_is_not_a_place_to_break_the_line() -> None:
    """Дефис - часть слова: «компьютерно-анимационный» рвать по нему незачем.

    Ширина взята та, на которой слово как раз упирается в край: разреши перенос по
    дефису - и строка кончилась бы огрызком «компьютерно-», а следующая началась бы с
    «анимационный», то есть одно слово читалось бы как два.
    """
    with outside(Outside(blurb=Fact(about=ABOUT), width=48)):
        rows = menu_rows(parts(("Тачки", 2006, 66)))

    assert not any(row.rstrip().endswith("-") for row in rows)
    assert any("компьютерно-анимационный" in row for row in rows)


def test_a_picture_without_a_reference_gets_exactly_the_line_it_got_before() -> None:
    """Справки нет - ни пустых разделителей, ни «не нашёл»: строка ровно та же.

    Скажи меню «справки нет» вслух - и на франшизе из тридцати пяти картин человек
    читал бы тридцать пять признаний вместо списка.
    """
    with outside(Outside(blurb=Fact())):
        said = "\n".join(menu_rows(parts(("Тачки", 2006, 66))))

    assert said == "  1. Тачки (2006)"


def test_a_picture_standing_outside_the_numbered_line_is_lined_like_any_other() -> None:
    """Пункт под линейкой франшизы подписан как все: подписи о номере части нет.

    Раскол при этом живёхонек - «Мультачки» стоят ПОД нумерованными «Тачками», и это
    решает порядок (:func:`~torrcast.domain.numbered_line._numbered_line`). Объяснялся
    он подписью в каждой такой строке, и 04-09-2026 владелец подпись снял: на «наруто»
    она стояла на 18 строках из 27 - подпись на всём читается не лучше подписи ни на чём.
    Строка тут дословная, а не собранная из тех же кусков: собранная приняла бы подпись
    назад молча.
    """
    cars = [
        plan("Тачки", 2006, part=1, seeders=66),
        plan("Тачки 2", 2011, part=2, seeders=40),
        plan("Тачки: Мультачки", 2008, seeders=10),
    ]
    _line, tail = _numbered_line([item.picture for item in cars])

    with outside(Outside()):
        rows = menu_rows(cars)

    assert [p.title for p in tail] == ["Тачки: Мультачки"], "пункт обязан стоять под линейкой"
    assert rows[2] == "  3. Тачки: Мультачки (2008)"


def test_the_reference_is_asked_about_a_picture_by_its_title_and_its_year() -> None:
    """Справка спрашивается по имени И году: у тёзок по имени она разная.

    Спроси меню одним именем - и «Мумия» 1999 года получила бы описание «Мумии» 2017-го,
    то есть чужое кино в строке, по которой человек и выбирает.
    """
    facts = Ready(
        {
            ("Мумия", 1999): Fact(about="Приключенческий фильм Стивена Соммерса."),
            ("Мумия", 2017): Fact(about="Перезапуск с Томом Крузом."),
        }
    )
    facts.start()

    with outside(Outside()):
        rows = menu_rows(parts(("Мумия", 1999, 47), ("Мумия", 2017, 58)), facts)

    assert rows[1].strip() == "Приключенческий фильм Стивена Соммерса."
    assert rows[3].strip() == "Перезапуск с Томом Крузом."


def test_an_english_menu_binds_each_russian_reference_to_its_own_picture() -> None:
    """Показ локален, но русский источник и кэш спрашиваются по внутреннему имени."""
    facts = Ready(
        {
            ("Титаник", 1997): Fact(about="James Cameron's epic romance."),
            ("Титаник: анатомия катастрофы", 1997): Fact(
                about="A documentary about the ship's sinking."
            ),
        }
    )
    facts.start()
    menu = [
        plan("Титаник", 1997, original="Titanic"),
        plan(
            "Титаник: анатомия катастрофы",
            1997,
            original="Titanic: Anatomy of a Disaster",
        ),
    ]

    _choose_tongue(EN)
    try:
        rows = menu_rows(menu, facts)
    finally:
        _choose_tongue(RU)

    assert rows[1].strip() == "James Cameron's epic romance."
    assert rows[3].strip() == "A documentary about the ship's sinking."
