"""Зеркало ручательства имени добора: справка и слова запроса ручаются, выдача - нет."""

from __future__ import annotations

from torrcast.domain.facts.origin import Origin
from torrcast.usecases.discover._proven_alt import _proven_alt


def test_the_wiki_title_vouches_for_the_top_up() -> None:
    assert _proven_alt("Up", "вверх", Origin(title="Up", year=2009))


def test_the_russian_name_of_the_wiki_vouches_for_the_top_up() -> None:
    assert _proven_alt("Тачки", "cars", Origin(name="Тачки"))


def test_a_transliteration_of_the_query_vouches_for_itself() -> None:
    from torrcast.domain.transliterate import transliterate

    assert _proven_alt(transliterate("психо"), "психо", Origin())


def test_a_name_read_off_a_release_vouches_for_nothing() -> None:
    """«The Climbers» из выдачи «Восхождения» ничем не подтверждён."""
    assert not _proven_alt("The Climbers", "восхождение", Origin())
