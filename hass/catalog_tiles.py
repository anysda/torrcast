"""Плитки каталога под один запрос: сперва офлайн-карта, следом подсказки IMDb.

Выдача поиска собиралась из имён найденных раздач, и пока индексеры молчали, плиток не было
вовсе: 1.2-8.6 с на стенде. Картины каталога известны раньше: карта имён отвечает сразу
(:class:`hass.catalog_index.CatalogIndex`), подсказчик IMDb - за 0.3-0.9 с и понимает
опечатку («интерстелар» - «Interstellar»). Раздачи догоняют их (:mod:`hass.catalog_merge`).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from hass.catalog_index import MIN_VOTES, SHOWN, CatalogIndex
from hass.search_results import _hit
from torrcast.domain.facts.imdb_rows import _TV_KINDS, _RuName
from torrcast.domain.json_value import JsonValue
from torrcast.domain.picture import Picture
from torrcast.domain.slugify import slugify

#: Ответ подсказчика IMDb на запрос: строки ``{"id", "l", "y", "qid", ...}``.
Suggest = Callable[[str], "list[dict[str, Any]]"]


class CatalogTiles:
    """Плитки одного запроса; подсказки спрашиваются один раз, фоном (:meth:`start`)."""

    def __init__(self, query: str, index: CatalogIndex, suggest: Suggest) -> None:
        self.query = query
        self.index = index
        self.suggest = suggest
        self._offline: list[JsonValue] | None = None
        self._online: list[JsonValue] = []
        self._lock = threading.Lock()

    def start(self, spawn: Callable[[Callable[[], None]], None]) -> CatalogTiles:
        spawn(self._ask)
        return self

    def tiles(self) -> list[JsonValue]:
        """Что известно сейчас: карта, а промолчала она - подсказки.

        Подсказчик ранжирует по славе, а не по имени, и рядом с «Рик и Морти» ставит
        «Старик и море»; его зовут туда, где карта не узнала имени: опечатка, чужое письмо.
        """
        with self._lock:
            if self._offline is None:
                self._offline = [_tile(*_named(row)) for row in self.index.look(self.query)]
            return list(self._offline or self._online)

    def _ask(self) -> None:
        try:
            rows = self.suggest(self.query)
        except Exception:  # подсказчик второй: его обрыв не отнимает у поиска карту
            rows = []
        tiles = [_tile(*named) for row in rows if (named := self._from(row)) is not None]
        with self._lock:
            self._online = tiles

    def _from(self, row: dict[str, Any]) -> tuple[str, str, int, str] | None:
        tconst, latin, year, kind = row.get("id"), row.get("l"), row.get("y"), row.get("qid")
        if not isinstance(latin, str) or not isinstance(year, int) or kind not in SHOWN:
            return None
        known = self.index.by_id(tconst) if isinstance(tconst, str) else None
        if self.index.votes().get(str(tconst), 0) < MIN_VOTES:
            return None
        title = known[4] if known is not None else latin
        return title, latin, year, "tv" if kind in _TV_KINDS else "movie"


def _named(row: _RuName) -> tuple[str, str, int | None, str]:
    _tconst, kind, original, year, name = row
    return (
        name,
        original,
        int(year) if year.isdigit() else None,
        "tv" if kind in _TV_KINDS else "movie",
    )


def _tile(title: str, original: str, year: int | None, kind: str) -> JsonValue:
    other = original if slugify(original) != slugify(title) else None
    picture = Picture(title, year, "tv" if kind == "tv" else "movie", other)
    return _hit(picture, 0, default=False)


__all__ = ["CatalogTiles", "Suggest"]
