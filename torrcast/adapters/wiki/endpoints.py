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
#: MediaWiki API даёт claims картины и обратный индекс заявлений без WDQS. Полка
#: родни не зависит от очереди и непредсказуемой цены SPARQL-сервиса.
WIKIDATA_API_HOST: Final = "www.wikidata.org"
WIKIDATA_API_PATH: Final = "/w/api.php"
#: Заголовок ответа Wikidata, которым SPARQL просят вернуть JSON.
SPARQL_HEAD: Final = {"Accept": "application/sparql-results+json"}
