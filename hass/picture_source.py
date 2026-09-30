"""Откуда мост берёт картинки: Википедия, а на промолчавших - IMDb.

Собрано в одном месте на обе двери намеренно. Картинку спрашивают список находок
(:class:`hass.hit_posters.HitPosters`) и карточка играющего (:class:`hass.posters.Posters`),
а полка у них общая: разойдись у них список источников - человек увидел бы в списке одну
картинку, а на экране другую, причём разошлись бы они молча.
"""

from __future__ import annotations

from hass.both_posters import BothPosters
from torrcast.adapters.wiki.imdb_poster import ImdbPoster
from torrcast.adapters.wiki.urgent_client import UrgentClient
from torrcast.adapters.wiki.wiki_poster import WikiPoster
from torrcast.runtime.facts_wiring import FACTS


def picture_source(urgent: bool = False, ahead: bool = False) -> BothPosters:
    """Источник картинок моста: оба источника по порядку доверия.

    ``urgent`` - картинки видимого списка: их запросы идут впереди полок и «похожих».
    ``ahead`` - те же полосы впереди фона, но спокойный порядок: второй источник спрашивается
    только о промахах первого, и ответ полный. Так спрашивает «Продолжить»: он не
    переспрашивается, и картинка, не названная в первом ответе, не встала бы вовсе.
    """
    client = UrgentClient(FACTS.client, urgent or ahead)
    return BothPosters(
        WikiPoster(client, client),
        ImdbPoster(client, client, FACTS.catalogue),
        client,
        urgent=urgent,
    )
