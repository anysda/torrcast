"""Зеркало паспортного имени: картина первого пула, названная справкой, а не вторым кругом."""

from __future__ import annotations

from tests.usecases.discover.world import franchise, pictures, row
from torrcast.domain.facts.origin import Origin
from torrcast.usecases.discover._passport_pick import _passport_pick

#: Короткий запрос «lain» сам по себе выбирает журнал, хотя в том же пуле есть сериал.
_ZINE = row("lainzine 1-5 [PDF]", "a", seeders=3)
_LAIN = row("Serial Experiments Lain (1998) BDRip 1080p", "b", seeders=44)
_POOL = pictures([_ZINE, _LAIN])


def test_the_passport_name_points_at_the_picture_the_query_missed() -> None:
    """Второй круг тут ничего не найдёт - он лишь повторит уже приехавшую картину."""
    about = Origin(title="Serial Experiments Lain", year=1998)
    found = franchise("lain", [_ZINE])

    named = _passport_pick(_POOL, about, found)

    assert named is not None
    assert [p.title for p in named] == ["Serial Experiments Lain"]


def test_a_name_pointing_at_what_we_already_took_changes_nothing() -> None:
    """Паспорт указал ровно на то, что и так нашли - второй круг тут ни при чём."""
    about = Origin(title="Serial Experiments Lain", year=1998)
    found = franchise("serial experiments lain", [_LAIN])

    assert _passport_pick(pictures([_LAIN]), about, found) is None


def test_a_year_that_argues_with_the_facts_is_not_taken() -> None:
    """Год картины спорит со справкой - это однофамилец, и брать его нельзя."""
    about = Origin(title="Serial Experiments Lain", year=2015)

    assert _passport_pick(_POOL, about, franchise("lain", [_ZINE])) is None


def test_a_silent_passport_names_nothing() -> None:
    """Справка промолчала - указывать некуда, и первый пул остаётся как был."""
    assert _passport_pick(_POOL, Origin(), franchise("lain", [_ZINE])) is None
