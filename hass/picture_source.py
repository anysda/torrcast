"""Откуда мост берёт картинки: Википедия, а на промолчавших - IMDb.

Собрано в одном месте на обе двери намеренно. Картинку спрашивают список находок
(:class:`hass.hit_posters.HitPosters`) и карточка играющего (:class:`hass.posters.Posters`),
а полка у них общая: разойдись у них список источников - человек увидел бы в списке одну
картинку, а на экране другую, причём разошлись бы они молча.
"""

from __future__ import annotations

from hass.both_posters import BothPosters
from torrcast.adapters.wiki.imdb_poster import ImdbPoster
from torrcast.adapters.wiki.wiki_poster import WikiPoster
from torrcast.runtime.facts_wiring import FACTS


def picture_source() -> BothPosters:
    """Источник картинок моста: оба источника по порядку доверия."""
    return BothPosters(
        WikiPoster(FACTS.client, FACTS.client),
        ImdbPoster(FACTS.client, FACTS.client, FACTS.catalogue),
        FACTS.client,
    )
