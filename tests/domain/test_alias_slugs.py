"""Зеркало :mod:`torrcast.domain.alias_slugs`: чужие имена картины помимо двух своих."""

from torrcast.domain.alias_slugs import _alias_slugs
from torrcast.domain.release import Release


def _named(*aliases: str) -> Release:
    return Release(raw_name="Брат 1997", title="Брат", aliases=aliases)


def test_the_two_names_the_picture_already_has_are_not_counted_as_extra() -> None:
    """Название и оригинал приходят отдельно, и повторять их среди прочих имён незачем."""
    group = [_named("Брат", "Brother", "Brat")]

    assert _alias_slugs(group, "Брат", "Brother") == ("brat",)


def test_the_extra_names_of_the_whole_group_come_together_and_in_order() -> None:
    """Имена собираются со всех раздач группы: в одной оно есть, в соседней нет."""
    group = [_named("Brat"), _named("Bratan"), _named("Brat")]

    assert _alias_slugs(group, "Брат", "Brother") == ("brat", "bratan")


def test_a_group_without_a_single_other_name_gives_nothing() -> None:
    assert _alias_slugs([_named("Брат")], "Брат", None) == ()
