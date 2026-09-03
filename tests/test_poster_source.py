"""Зеркало :mod:`hass.poster_source`: договор списка находок с источником постеров."""

from __future__ import annotations

from hass.poster_source import PosterSource
from torrcast.adapters.wiki.wiki_poster import WikiPoster
from torrcast.runtime.facts_wiring import FACTS


def test_the_real_wikipedia_adapter_answers_this_very_contract() -> None:
    """🔴 Договор описан ради настоящего источника, а не ради двойника проб.

    Разъедься он с адаптером, каждая проба списка осталась бы зелёной на своей подделке,
    а живой мост падал бы на первом же поиске.
    """
    made = WikiPoster(FACTS.client, FACTS.client)
    assert isinstance(made, PosterSource)


def test_a_source_that_only_judges_is_not_a_source() -> None:
    """Договор из двух шагов: приговор на месте и байты следом; одного шага мало."""

    class Half:
        def wanted(self, asks: object, timeout: float) -> dict[object, list[str]]:
            return {}

    assert not isinstance(Half(), PosterSource)
