"""Картины каталога по началу имени, без сети: русское прокатное имя и оригинал.

Строка поиска показывает картины до того, как ответят индексеры (:mod:`hass.catalog_tiles`),
и первым делом спрашивает офлайн-карту выгрузки IMDb (:class:`~torrcast.adapters.wiki.
imdb_names.ImdbNames`): она уже лежит в памяти моста (:mod:`hass.warm_facts`). Карта знает
картину по русскому имени, а указатель добавляет вход по оригиналу: «The Matrix» - это
«Матрица». Голоса IMDb отсекают шум: безвестный тёзка погас бы на экране, но место занял бы.
"""

from __future__ import annotations

import threading
from bisect import bisect_left
from collections.abc import Callable
from typing import Final

from torrcast.domain.facts.imdb_rows import _RuName
from torrcast.domain.slugify import slugify

#: Какие записи выгрузки строка поиска показывает: эпизоды, короткий метр и игры - шум.
SHOWN: Final = frozenset({"movie", "tvMovie", "tvSeries", "tvMiniSeries"})
#: Сколько голосов IMDb нужно картине, чтобы встать плиткой.
MIN_VOTES: Final = 1000
#: Во сколько раз картина может уступать голосами самой известной под тем же запросом:
#: «гравит» - это «Гравитация» и «Гравити Фолз», а не сериал 2010 года с тысячей голосов.
SHARE: Final = 100
#: Сколько картин отдаёт указатель на один запрос.
LIMIT: Final = 8
#: Короче этого запрос ещё не имя: две буквы подходят к десяткам тысяч картин.
SHORTEST: Final = 3


class CatalogIndex:
    """Указатель по началу имени; пока его не собрали (:meth:`warm`), он молчит."""

    def __init__(
        self,
        names: Callable[[], dict[str, list[_RuName]]],
        votes: Callable[[], dict[str, int]],
    ) -> None:
        self.names = names
        self.votes = votes
        self._keys: list[str] = []
        self._rows: dict[str, list[_RuName]] = {}
        self._ids: dict[str, _RuName] = {}
        self._ready = False
        self._lock = threading.Lock()

    def warm(self) -> None:
        """Собрать указатель; зовётся фоном на старте, первый поиск его не ждёт."""
        rows: dict[str, list[_RuName]] = {}
        ids: dict[str, _RuName] = {}
        for slug, named in self.names().items():
            for row in named:
                ids.setdefault(row[0], row)
                rows.setdefault(slug, []).append(row)
                original = slugify(row[2]) if row[2] else ""
                if original and original != slug:
                    rows.setdefault(original, []).append(row)
        self.votes()  # голоса разбираются тут же, а не первым поиском
        with self._lock:
            self._rows, self._ids, self._keys = rows, ids, sorted(rows)
            self._ready = True

    def look(self, query: str) -> list[_RuName]:
        """Картины, чьё имя начинается с запроса: точное имя первым, дальше по голосам."""
        slug = slugify(query)
        with self._lock:
            if not self._ready or len(slug) < SHORTEST:
                return []
            keys, rows = self._keys, self._rows
        votes = self.votes()
        found: dict[str, tuple[bool, _RuName]] = {}
        at = bisect_left(keys, slug)
        while at < len(keys) and keys[at].startswith(slug):
            for row in rows[keys[at]]:
                if row[1] in SHOWN and (row[0] not in found or keys[at] == slug):
                    found[row[0]] = (keys[at] == slug, row)
            at += 1
        top = max((votes.get(tconst, 0) for tconst in found), default=0)
        floor = max(MIN_VOTES, top // SHARE)
        kept = [pair for pair in found.values() if votes.get(pair[1][0], 0) >= floor]
        kept.sort(key=lambda pair: (not pair[0], -votes.get(pair[1][0], 0)))
        return [row for _, row in kept[:LIMIT]]

    def by_id(self, tconst: str) -> _RuName | None:
        """Строка карты по IMDb-id: подсказка IMDb зовёт картину латиницей, карта - по-русски."""
        with self._lock:
            return self._ids.get(tconst)


__all__ = ["LIMIT", "MIN_VOTES", "SHARE", "SHORTEST", "SHOWN", "CatalogIndex"]
