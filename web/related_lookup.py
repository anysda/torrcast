"""Родня картины (другие части франшизы) без ожидания сети: фоновый добор с кэшем.

Тот же приём, что у :class:`web.episode_lookup.EpisodeLookup`: карточка не ждёт
Wikidata, а спрашивает кэш и заводит фон, если его там ещё нет. ``None`` значит
«ещё не готово» и тянет за собой :data:`web.card._PARTIAL`; пустой список -
законченный ответ «родни не нашлось» (§8), а не недоезд.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from hass.hit_posters import hits
from torrcast.domain.catalogs.tongue import EN, tongue
from torrcast.domain.facts.kin import Kin
from torrcast.domain.facts.origin import Origin
from torrcast.domain.json_value import JsonValue
from torrcast.domain.slugify import slugify
from torrcast.domain.spoken_title import spoken_title

#: Тот же ``FranchiseKin.of``: имя, серия ли картина, срок сети - родня.
Franchise = Callable[[str, bool, float], list[Kin]]
#: Тот же ``Passport.of``: паспорт родни латиницей - Wikidata своего не называет
#: (:func:`_seed`).
PassportOf = Callable[[str, bool, float], Origin]
#: Тот же ``HitPosters.offer``: те же записи, с обложкой у тех, кому она нашлась.
Offer = Callable[[list[JsonValue]], list[JsonValue]]
Spawn = Callable[[Callable[[], None]], None]
TIMEOUT = 8.0
RETRY = 3600.0
#: Та же форма, что у плитки полок (:data:`web.shelves_cache._TILE_FIELDS`) - страница
#: рисует обе плитки одним и тем же кодом, а не двумя похожими. ``shown`` - имя ДЛЯ
#: ЧЕЛОВЕКА, ``title`` остаётся записанным ради розыска обложки и ``query``.
_TILE_FIELDS: tuple[str, ...] = (
    "key",
    "title",
    "shown",
    "year",
    "kind",
    "quality",
    "poster",
    "query",
)


def _daemon(job: Callable[[], None]) -> None:
    threading.Thread(target=job, daemon=True, name="related-lookup").start()


def _no_passport(_title: str, _series: bool, _timeout: float) -> Origin:
    """Паспорт по умолчанию: без проводки родня остаётся под записанным именем."""
    return Origin()


def _seed(kin: Kin, original: str) -> dict[str, JsonValue]:
    """Плитка родни до обложки: ``original`` в ней только на розыск обложки, не на показ.

    Wikidata не называет род родни - франшизы приёмки (§8) все до одной кино, и это
    умолчание, а не подпорка под конкретное название. Латиница - паспорт того же имени
    (:func:`torrcast.usecases.passport.Passport.of`), каким гейт добора проверяет саму
    картину; нет статьи на другом языке - латиницы у родни тоже нет, и это честно.
    """
    return {
        "key": f"movie:{slugify(kin.name)}:{kin.year or 0}",
        "title": kin.name,
        "shown": spoken_title(kin.name, original),
        "year": kin.year,
        "kind": "movie",
        "quality": None,
        "query": kin.name,
        "original": original,
    }


def _project(record: JsonValue) -> JsonValue:
    """Ужать плитку под контракт: обложка обещана, а розыскное ``original`` - нет."""
    if not isinstance(record, dict):
        return record
    return {field_name: record.get(field_name) for field_name in _TILE_FIELDS}


@dataclass
class RelatedLookup:
    """Кэш родни на процесс: первый вопрос о картине заводит фон, а не ждёт его."""

    franchise: Franchise
    offer: Offer = hits.offer
    passport: PassportOf = _no_passport
    spawn: Spawn = _daemon
    clock: Callable[[], float] = time.monotonic
    _tiles: dict[str, tuple[list[JsonValue], float]] = field(default_factory=dict)
    _pending: set[str] = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def of(self, title: str, series: bool) -> list[JsonValue] | None:
        now = self.clock()
        with self._lock:
            cached = self._tiles.get(title)
            if cached is not None and cached[1] > now:
                return cached[0]
            if title in self._pending:
                return None
            self._pending.add(title)
        self.spawn(lambda: self._build(title, series))
        with self._lock:
            cached = self._tiles.get(title)
            return cached[0] if cached is not None else None

    def _build(self, title: str, series: bool) -> None:
        found = self.franchise(title, series, TIMEOUT)
        seeds: list[JsonValue] = [_seed(kin, self._latin_of(kin.name)) for kin in found]
        tiles = [_project(record) for record in self.offer(seeds)]
        with self._lock:
            self._tiles[title] = (tiles, self.clock() + RETRY)
            self._pending.discard(title)

    def _latin_of(self, name: str) -> str:
        """Латиница родни из паспорта - под русским языком показ на неё не смотрит.

        Не звать паспорт впустую (:func:`torrcast.domain.spoken_title.spoken_title`
        под русским отвечает записью в любом случае) - Wikipedia не спрашивают ради
        ответа, который никто не прочитает.
        """
        return self.passport(name, False, TIMEOUT).title if tongue() == EN else ""


__all__ = ["Franchise", "PassportOf", "RelatedLookup", "Spawn"]
