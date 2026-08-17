"""Заготовки выдачи, индикатора и клиента индексеров для зеркал пакета добора.

Отдельным файлом, а не фикстурой: круги добора спрашивают выдачу целиком, и собирать
один и тот же индексер в каждом из пятнадцати зеркал значило бы разводить редакции.
"""

from __future__ import annotations

from typing import Any

import torrcast.reinforce  # noqa: F401  - импорт фасада и есть связывание портов добора
from torrcast.domain.cluster import cluster
from torrcast.domain.pick_franchise import pick_franchise
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.ports.torrent_catalogue import RawRow
from torrcast.search import RawResult, merge, to_releases

GB = 1024**3


def row(
    title: str, tag: str = "a", *, seeders: int = 50, size_gb: float = 8.0, indexer: str = "Nyaa.si"
) -> RawResult:
    """Одна строка выдачи каталога; инфохэш подделываем из тега."""
    return RawResult(
        title=title,
        info_hash=tag * 40,
        size=int(size_gb * GB),
        seeders=seeders,
        indexer=indexer,
    )


def releases(rows: list[RawResult]) -> list[Release]:
    """Раздачи, разобранные тем же каталогом, что стоит за портом добора."""
    return to_releases(rows)


def pictures(rows: list[RawResult]) -> list[Picture]:
    """Картины выдачи: тот же кластер, что собирает меню."""
    return cluster(to_releases(rows))


def franchise(query: str, rows: list[RawResult]) -> list[Picture]:
    """Картины запроса: то, что круг добора и получает на вход."""
    return pick_franchise(query, pictures(rows))


class Catalogue:
    """Каталог раздач договором порта; сам разбор считает тот же парсер, что и в бою."""

    def merge(self, *batches: list[RawRow]) -> list[RawRow]:
        return merge(*batches)

    def to_releases(self, rows: list[RawRow]) -> list[Release]:
        return to_releases(rows)


class Said:
    """Индикатор, который ничего не рисует, а запоминает сказанное."""

    def __init__(self) -> None:
        self.notes: list[str] = []
        self.phases: list[str] = []

    def phase(self, text: str) -> None:
        self.phases.append(text)

    def note(self, text: str) -> None:
        self.notes.append(text)

    def stop(self) -> None:
        return None

    def __enter__(self) -> Said:
        return self

    def __exit__(self, *_exc: Any) -> None:
        return None

    @property
    def text(self) -> str:
        """Всё, что осталось на экране, одной строкой."""
        return "\n".join(self.notes)


class Indexer:
    """Клиент индексеров: отвечает заготовленным и помнит, о чём его спросили."""

    def __init__(
        self,
        rows: list[RawResult] | None = None,
        *,
        spare: float = 9.0,
        capped: tuple[str, ...] = (),
    ) -> None:
        self._rows = list(rows or [])
        self._spare = spare
        #: Те, кто закрыл выдачу своим потолком, - ровно то поле, что читает повод круга.
        self.capped = capped
        self.asked: list[str] = []
        #: Частный бюджет за целью ещё не выдан - как у свежего клиента поиска.
        self.over_goal = False

    def spare(self) -> float:
        return self._spare

    def search(self, query: str) -> list[RawResult]:
        self.asked.append(query)
        return list(self._rows)
