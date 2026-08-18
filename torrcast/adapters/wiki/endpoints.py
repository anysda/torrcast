"""Адреса источников справки; их зовут адаптеры Википедии и Wikidata."""

from __future__ import annotations

from typing import Final

WIKI_HOST: Final = "ru.wikipedia.org"
WIKI_PATH: Final = "/w/api.php"
WIKIDATA_HOST: Final = "query.wikidata.org"
WIKIDATA_PATH: Final = "/sparql"
#: Заголовок ответа Wikidata, которым SPARQL просят вернуть JSON.
SPARQL_HEAD: Final = {"Accept": "application/sparql-results+json"}
