"""Проводка справки: единственное место, где её сценарии видят свои адаптеры."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Final

from torrcast.adapters.filesystem.state.state_path import state_path
from torrcast.adapters.wiki.facts_file_cache import FactsFileCache
from torrcast.adapters.wiki.http_json_client import HttpJsonClient
from torrcast.adapters.wiki.imdb_names import ImdbNames
from torrcast.adapters.wiki.imdb_ratings import ImdbRatings
from torrcast.adapters.wiki.state_json_store import StateJsonStore
from torrcast.adapters.wiki.text_file_source import TextFileSource
from torrcast.adapters.wiki.wiki_articles import WikiArticles
from torrcast.adapters.wiki.wiki_blurbs import WikiBlurbs
from torrcast.adapters.wiki.wiki_spelling import WikiSpelling
from torrcast.adapters.wiki.wikidata_dates import WikidataDates
from torrcast.domain.facts.settings import USER_AGENT
from torrcast.usecases.passport import Passport


def _beside_state() -> Path:
    """Кэш справки лежит рядом с состоянием - и переезжает вместе с ним."""
    return state_path().with_name("facts.json")


class FactsWiring:
    """Собранная справка: один клиент, один кэш и оба её сценария.

    Всё строится один раз на процесс: у клиента память разрешённых адресов, у карты имён
    и оценок - разобранные выгрузки, и терять их между вызовами незачем. ``where``
    спрашивается на каждом обращении к кэшу: каталог состояния меняется на лету.
    """

    def __init__(self, where: Callable[[], Path] = _beside_state) -> None:
        self.client = HttpJsonClient(USER_AGENT)
        self.ratings = ImdbRatings(TextFileSource())
        self.catalogue = ImdbNames(TextFileSource(), self.ratings)
        self.cache = FactsFileCache(StateJsonStore(where))
        self.articles = WikiArticles(self.client, WikiSpelling(self.client), self.catalogue)
        self.blurbs = WikiBlurbs(self.client, self.ratings)
        self.passport = Passport(
            self.articles, self.catalogue, self.cache, WikidataDates(self.client)
        )


#: Проводка справки на весь процесс: один HTTPS-клиент со своей памятью адресов, один
#: кэш рядом с состоянием и разобранные однажды выгрузки IMDb.
FACTS: Final = FactsWiring()
