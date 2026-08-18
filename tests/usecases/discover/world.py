"""Заготовки выдачи, индикатора и клиента индексеров для зеркал пакета поиска.

Отдельным файлом, а не фикстурой: круг поиска спрашивает выдачу целиком, и собирать
один и тот же индексер в каждом из зеркал значило бы разводить редакции.
"""

from __future__ import annotations

from typing import Any

from torrcast.domain.cluster import cluster
from torrcast.domain.facts.origin import Origin
from torrcast.domain.pick_franchise import pick_franchise
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.ports.torrent_catalogue import RawRow
from torrcast.search import RawResult, merge, to_releases
from torrcast.usecases.discover._search_state import _configure_discover

GB = 1024**3


def row(
    title: str, tag: str = "a", *, seeders: int = 50, size_gb: float = 8.0, indexer: str = "Nyaa.si"
) -> RawResult:
    """Одна строка выдачи каталога; инфохэш подделываем из тега."""
    return RawResult(
        title=title, info_hash=tag * 40, size=int(size_gb * GB), seeders=seeders, indexer=indexer
    )


def releases(rows: list[RawResult]) -> list[Release]:
    """Раздачи, разобранные тем же каталогом, что стоит за портом поиска."""
    return to_releases(rows)


def pictures(rows: list[RawResult]) -> list[Picture]:
    """Картины выдачи: тот же кластер, что собирает меню."""
    return cluster(to_releases(rows))


def franchise(query: str, rows: list[RawResult]) -> list[Picture]:
    """Картины запроса: то, что круг поиска и получает на вход."""
    return pick_franchise(query, pictures(rows))


class Catalogue:
    """Каталог раздач договором порта; разбор считает тот же парсер, что и в бою."""

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
        answers: dict[str, list[RawResult]] | None = None,
        silent: tuple[str, ...] = (),
        banned: tuple[str, ...] = (),
    ) -> None:
        self._rows = list(rows or [])
        self._answers = answers or {}
        self._spare = spare
        self.asked: list[str] = []
        self.floors: list[float] = []
        #: Счёт молчунов - тот же, что читает круг поиска у боевого клиента.
        self.silent = silent
        self.banned = banned
        self.reported_silent: set[str] = set()
        #: Частный бюджет за целью ещё не выдан - как у свежего клиента поиска.
        self.over_goal = False
        #: Пол бюджета круга: заходы его двигают, договор клиента о нём знает.
        self.cap_floor = 1.0

    def spare(self) -> float:
        return self._spare

    def late(self) -> list[RawResult]:
        """Опоздавших нет: круг тут отвечает разом (TC-118)."""
        return []

    def search(self, query: str) -> list[RawResult]:
        self.asked.append(query)
        self.floors.append(self.cap_floor)
        return list(self._answers.get(query.casefold(), self._rows))


def wire_catalogue(passport: Origin | None = None) -> None:
    """Дать поиску его внешний мир: разбор выдачи и молчащую справку о картинах."""
    _configure_discover(
        Catalogue(),
        lambda *_args, **_kwargs: passport or Origin(),
        lambda *_args, **_kwargs: Indexer(),
    )
