"""Зеркало :mod:`torrcast.domain.free_first`: безномерная первая часть у нумерованных."""

from torrcast.domain.free_first import _free_first
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release


def _picture(title: str, year: int | None, original: str | None = None, copies: int = 1) -> Picture:
    return Picture(
        title=title,
        year=year,
        original=original,
        releases=[Release(raw_name=title, title=title) for _ in range(copies)],
    )


NUMBERED = [Picture(title="Брат 2", year=2000, original="Brother 2", part=2)]


def test_the_picture_named_by_the_franchise_itself_is_the_first_part() -> None:
    """У первой части номера нет: её имя и есть имя франшизы."""
    found = _free_first([_picture("Брат", 1997)], NUMBERED)

    assert found is not None
    assert found.title == "Брат"


def test_a_stranger_is_not_taken_for_the_first_part() -> None:
    """Ни своим именем, ни латинским корнем к франшизе не привязана - значит, чужая."""
    assert (
        _free_first([_picture("Матрица: Перезагрузка", 2003, "The Matrix: Reloaded")], NUMBERED)
        is None
    )


def test_the_liveliest_of_the_earlier_ones_takes_the_place() -> None:
    """Раньше нумерованных их несколько - берём ту, у которой раздач больше."""
    found = _free_first(
        [_picture("Брат", 1997, copies=1), _picture("Брат", 1995, copies=7)], NUMBERED
    )

    assert found is not None
    assert found.year == 1995


def test_nothing_to_choose_from_is_an_honest_nothing() -> None:
    assert _free_first([], NUMBERED) is None


#: Строка сериала начинается со ВТОРОГО номера и ровесница своего соседа: ровно эта
#: пара приезжает по запросу «One Punch Man» с живой выдачи (2015 у обеих).
OVA_NUMBERED = [Picture(title="Ванпанчмен", year=2015, original="One Punch Man", part=2)]


def test_a_kinsman_no_older_than_the_line_does_not_head_it() -> None:
    """🔴 TC-982. Родня по корню оригинала берёт голову только вместе с ГОДОМ.

    «Путь к становлению героем» - 24-минутная OVA: своим именем она франшизу не
    называет и попадает в кандидаты лишь корнем оригинала ``One Punch Man``. Раньше
    сериала она не вышла - значит первой частью не была, и головы у строки нет вовсе.
    Пока голову отдавали первому кандидату подряд, голый Enter уезжал на эту OVA
    мимо самого сериала.
    """
    ova = _picture("Ванпанчмен: Путь к становлению героем", 2015, "One Punch Man: Road to Hero")

    assert _free_first([ova], OVA_NUMBERED) is None


def test_a_kinsman_older_than_the_line_still_heads_it() -> None:
    """Тот же сосед, вышедший РАНЬШЕ строки, головой остаётся: это её начало."""
    earlier = _picture("Ванпанчмен: Путь к становлению героем", 2014, "One Punch Man: Road to Hero")

    found = _free_first([earlier], OVA_NUMBERED)

    assert found is not None and found.year == 2014


def test_the_franchises_own_name_heads_the_line_without_being_older() -> None:
    """⚠️ Голое имя проверку годом не проходит и проходить не должно.

    «сёгун s1e9» даёт нумерованной строкой чужую «Радость пытки 2: Садизм сегуна»
    (1976), и обе «Сёгун» моложе неё. Отними у голого имени право на голову - и меню
    возглавит чужая картина, у которой номер части взялся из названия.
    """
    stranger = [Picture(title="Радость пытки 2: Садизм сегуна", year=1976, part=2)]

    found = _free_first([_picture("Сёгун", 1980, "Shogun")], stranger)

    assert found is not None and found.title == "Сёгун"
