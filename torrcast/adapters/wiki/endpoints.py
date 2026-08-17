"""Адреса источников справки; их зовут адаптеры Википедии и Wikidata."""

from __future__ import annotations

from typing import Final

_WIKI_HOST: Final = "ru.wikipedia.org"
_WIKI_PATH: Final = "/w/api.php"
_WIKIDATA_HOST: Final = "query.wikidata.org"
_WIKIDATA_PATH: Final = "/sparql"
#: Заголовок ответа Wikidata, которым SPARQL просят вернуть JSON.
_SPARQL_HEAD: Final = {"Accept": "application/sparql-results+json"}
