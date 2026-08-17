"""Проверяет дописывание второго источника в отметку паспорта."""

from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.settings import SOURCE_MAP, SOURCE_WIKI
from torrcast.domain.facts.with_source import with_source


def test_two_sources_are_named_in_the_order_they_answered() -> None:
    """«wiki+map» - имя дала статья, год дописала карта, и порядок тут значащий."""
    found = with_source(Origin(title="Cars", source=SOURCE_WIKI), SOURCE_MAP)
    assert found.source == "wiki+map"


def test_an_empty_addition_and_a_repeat_are_not_written() -> None:
    """Отметка описывает источники, а не число обращений к ним."""
    wiki = Origin(title="Cars", source=SOURCE_WIKI)
    assert with_source(wiki, "") == wiki
    assert with_source(wiki, SOURCE_WIKI) == wiki
