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

from torrcast.domain.asked_year import asked_year
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
#: From this many letters one missed letter is a typo rather than another word.
TYPO_FROM: Final = 5


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
        self._built = threading.Event()

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
        self._built.set()

    def ready(self, wait: float = 0.0) -> bool:
        """The index is built: an empty answer is final, not a cold start."""
        return self._built.wait(wait) if wait > 0 else self._built.is_set()

    def look(self, query: str) -> list[_RuName]:
        """Картины, чьё имя начинается с запроса: точное имя первым, дальше по голосам."""
        with self._lock:
            if not self._ready:
                return []
            keys, rows = self._keys, self._rows
        slug = slugify(query)
        name, year = asked_year(query)
        if year is not None and not _starting(keys, slug):
            # «Интерстелар 2014»: the year narrows the picture, it is not part of a name.
            slug = slugify(name)
        votes = self.votes()
        kept = _kept(self._found(keys, rows, slug), votes)
        if not kept and len(slug) >= TYPO_FROM and not any(ch.isdigit() for ch in slug):
            # One missed letter is a typo, not another title (the idea of Stremio local-search);
            # an unknown namesake of the typo («Interstelar», no votes) does not stop it.
            found: dict[str, tuple[bool, _RuName]] = {}
            for key in _starting_with(keys, slug[0]):
                if any(_one_edit(slug, key[:size]) for size in range(len(slug) - 1, len(slug) + 2)):
                    found.update((row[0], (False, row)) for row in rows[key] if row[1] in SHOWN)
            kept = _kept(found, votes)
        return [row for _, row in kept[:LIMIT]]

    def _found(
        self, keys: list[str], rows: dict[str, list[_RuName]], slug: str
    ) -> dict[str, tuple[bool, _RuName]]:
        found: dict[str, tuple[bool, _RuName]] = {}
        if len(slug) < SHORTEST:
            # Two letters start thousands of titles, but an exact short name is a picture: «Мы».
            exact = rows.get(slug, []) if slug else []
            return {row[0]: (True, row) for row in exact if row[1] in SHOWN}
        at = bisect_left(keys, slug)
        while at < len(keys) and keys[at].startswith(slug):
            for row in rows[keys[at]]:
                if row[1] in SHOWN and (row[0] not in found or keys[at] == slug):
                    found[row[0]] = (keys[at] == slug, row)
            at += 1
        return found

    def by_id(self, tconst: str) -> _RuName | None:
        """Строка карты по IMDb-id: подсказка IMDb зовёт картину латиницей, карта - по-русски."""
        with self._lock:
            return self._ids.get(tconst)


def _kept(
    found: dict[str, tuple[bool, _RuName]], votes: dict[str, int]
) -> list[tuple[bool, _RuName]]:
    """Known pictures only, the exact name first and then by votes."""
    top = max((votes.get(tconst, 0) for tconst in found), default=0)
    floor = max(MIN_VOTES, top // SHARE)
    kept = [pair for pair in found.values() if votes.get(pair[1][0], 0) >= floor]
    kept.sort(key=lambda pair: (not pair[0], -votes.get(pair[1][0], 0), pair[1][0]))
    return kept


def _starting(keys: list[str], slug: str) -> bool:
    at = bisect_left(keys, slug)
    return at < len(keys) and keys[at].startswith(slug)


def _starting_with(keys: list[str], letter: str) -> list[str]:
    """Keys of one first letter: a typo rarely starts a word."""
    return keys[bisect_left(keys, letter) : bisect_left(keys, chr(ord(letter) + 1))]


def _one_edit(left: str, right: str) -> bool:
    """The two strings differ by exactly one insertion, deletion or replacement."""
    if abs(len(left) - len(right)) > 1 or left == right:
        return False
    at = next((n for n, (a, b) in enumerate(zip(left, right, strict=False)) if a != b), None)
    if at is None:
        return True
    if len(left) == len(right):
        return left[at + 1 :] == right[at + 1 :]
    shorter, longer = (left, right) if len(left) < len(right) else (right, left)
    return shorter[at:] == longer[at + 1 :]


__all__ = ["LIMIT", "MIN_VOTES", "SHARE", "SHORTEST", "SHOWN", "TYPO_FROM", "CatalogIndex"]
