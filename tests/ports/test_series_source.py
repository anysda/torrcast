"""Контракт каталога сериала: ему отвечают и каталог карточки, и сборка юнита."""

from torrcast.ports.series_source import Aired, SeriesSource
from torrcast.runtime.series_facts import SeriesFacts
from web.series_catalog import SeriesCatalog


def test_the_card_catalogue_and_the_unit_catalogue_are_the_same_port() -> None:
    """Плашка и юнит спрашивают серию одним правилом: каталоги обязаны быть взаимозаменяемы."""
    numbers = {1: (1, 2)}

    def ids(*_a: object) -> str:
        return "tt1"

    def aired(*_a: object) -> Aired:
        return {}, False

    def now() -> str:
        return "2026-01-01T00:00:00+00:00"

    card: SeriesSource = SeriesCatalog(ids, lambda _t: numbers, aired, now)
    unit: SeriesSource = SeriesFacts(ids, lambda _t: numbers, aired, now)
    for port in (card, unit):
        assert port.ids("Show", "", None) == "tt1"
        assert port.numbers("tt1") == numbers
        assert port.aired("tt1", 0.0) == ({}, False)
        assert port.now() == "2026-01-01T00:00:00+00:00"
