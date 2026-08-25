"""Зеркало :mod:`torrcast.domain.compose`: одна картина из горсти раздач о ней."""

from torrcast.domain.compose import _compose
from torrcast.domain.release import Release


def _named(title: str, original: str | None = None, aliases: tuple[str, ...] = ()) -> Release:
    return Release(raw_name=title, title=title, original=original, year=1997, aliases=aliases)


def test_the_russian_title_wins_over_a_latin_one_however_many_carry_it() -> None:
    """Человеку показывается русское название, даже когда латинских раздач больше."""
    group = [_named("Bratuha"), _named("Bratuha"), _named("Брат", "Brother")]

    assert _compose("movie", 1997, group).title == "Брат"


def test_a_group_of_latin_names_only_keeps_the_one_most_releases_wrote() -> None:
    """Русского имени нет вовсе - тогда решает большинство, а не первая раздача."""
    group = [_named("Bratuha"), _named("Brother"), _named("Brother")]

    assert _compose("movie", 1997, group).title == "Brother"


def test_the_other_names_of_the_group_become_the_aliases_of_the_picture() -> None:
    """Имена, которыми картину зовут раздачи, - вход в неё для следующего запроса."""
    group = [_named("Брат", "Brother", aliases=("Bratan", "Брат"))]

    assert _compose("movie", 1997, group).aliases == ("bratan",)


def test_the_part_number_is_read_out_of_the_title() -> None:
    """Номер части приходит из названия: отдельного поля у раздачи для него нет."""
    assert _compose("movie", 2000, [_named("Брат 2"), _named("Брат 2")]).part == 2
    assert _compose("movie", 1997, [_named("Брат")]).part is None


def test_the_whole_group_stays_inside_the_picture() -> None:
    """Картина - это её раздачи: отбор идёт по ним, и терять их тут нельзя."""
    group = [_named("Брат", "Brother"), _named("Брат", "Brother")]

    assert len(_compose("movie", 1997, group).releases) == 2
