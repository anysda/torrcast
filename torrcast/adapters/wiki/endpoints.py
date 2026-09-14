"""Адреса источников справки; их зовут адаптеры Википедии и Wikidata."""

from __future__ import annotations

from typing import Final

WIKI_HOST: Final = "ru.wikipedia.org"
WIKI_PATH: Final = "/w/api.php"
#: Английский раздел. Постер спрашивается прежде всего тут, но НЕ только тут: русский
#: раздел несвободные обложки держит - локально, на своём хосте
#: (:class:`~torrcast.adapters.wiki.poster_files.PosterFiles`).
EN_WIKI_HOST: Final = "en.wikipedia.org"
WIKIDATA_HOST: Final = "query.wikidata.org"
WIKIDATA_PATH: Final = "/sparql"
#: Заголовок ответа Wikidata, которым SPARQL просят вернуть JSON.
SPARQL_HEAD: Final = {"Accept": "application/sparql-results+json"}
