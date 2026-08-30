"""Кэш справки и паспортов в одном JSON-хранилище; зовут оба сценария справки."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable

from torrcast.domain.catalogs.tongue import tongue
from torrcast.domain.facts.cache_rows import (
    _cached_facts,
    _fact_rows,
    _origin_key,
    _origin_row,
    _row_origin,
)
from torrcast.domain.facts.fact import Fact
from torrcast.domain.facts.origin import Origin
from torrcast.ports.json_store import JsonStore


class FactsFileCache:
    """Паспорта и справка лежат в одном файле, но в своих рядах ключей.

    Не вышло записать — молчим: это не путь показа. Битое или отсутствующее хранилище
    равно пустому, и справка просто перечитается из сети.
    """

    def __init__(self, store: JsonStore, now: Callable[[], float] = time.time) -> None:
        self.store = store
        self.now = now

    def read(self, title: str, series: bool | None) -> Origin | None:
        """Что лежит в кэше. ``None`` — не спрашивали; пустой паспорт — спрашивали, нет его."""
        return _row_origin(self.store.read().get(_origin_key(title, series)))

    def write(self, title: str, series: bool | None, found: Origin) -> None:
        """Дописать паспорт к тому, что уже лежит в хранилище."""
        raw = self.store.read()
        raw[_origin_key(title, series)] = _origin_row(found)
        self.store.write(raw)

    def blurbs(self, wanted: list[tuple[str, int | None]]) -> dict[tuple[str, int | None], Fact]:
        """Что уже лежит на диске и ещё не протухло; за остальным пойдут в сеть.

        Язык продукта спрашивается тут, а не хранится: полка общая на все языки, и ряд
        берётся с той её части, на которой говорит нынешний прогон
        (:func:`~torrcast.domain.facts.cache_rows._key`).
        """
        return _cached_facts(self.store.read(), wanted, self.now(), tongue())

    def remember(
        self,
        found: dict[tuple[str, int | None], Fact],
        misses: Iterable[tuple[str, int | None]] = (),
    ) -> None:
        """Дописать итог похода в кэш; нечего дописывать - хранилище не трогаем."""
        blanks = list(misses)
        if not found and not blanks:
            return
        raw = self.store.read()
        raw.update(_fact_rows(found, blanks, int(self.now()), tongue()))
        self.store.write(raw)
