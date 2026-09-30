"""Один заход сборки обеих полок: на холодном экземпляре видимое раньше приговоров.

Холодная полка ждала 85-254 с, из них около 87% - приговоры «играет ли» по одному
(замер TC-1322). Холодный заход показывает плитки, как только легли байты обложки, и
доводит приговоры фоном несколькими руками (:func:`web.shelf_judge.shelf_judge`): «не
играет» снимает плитку, «не знаю» её не трогает (:func:`web.shelf_tiles._covered`).
Тёплый заход до приговоров не показывает: на экране уже проверенная полка. Показ до
приговоров идёт без клейма правила (:mod:`web.built_by_rule`).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final, Protocol

from torrcast.domain.feed_row import FeedRow
from torrcast.domain.json_value import JsonValue
from torrcast.domain.picture import Picture
from torrcast.ports.torrent_catalogue.torrent_catalogue import TorrentCatalogue
from torrcast.usecases.shelves.fresh_shelf import LIMIT
from web.build_shelf import build_shelf
from web.built_by_rule import FIELD, RULE
from web.cold import SHELVES, cold
from web.drop_count import DropCount
from web.shelf_judge import Verdict, shelf_judge
from web.shelf_lane import shelf_lane
from web.shelf_pictures import shelf_pictures
from web.shelf_seeds import shelf_seeds
from web.shelf_tiles import Offer, PassportOf, Playable, shelf_tiles

#: Сколько холодный заход ждёт доезда обложек, прежде чем считать очередь полки полной:
#: гонка источников отвечает за 1.5 с, опоздавшие ложатся до ~24 с (:mod:`hass.both_posters`).
FILL_BY: Final = 25.0


class _Cache(Protocol):
    """Что заход берёт у :class:`web.shelves_cache.ShelvesCache` (без цикла импортов)."""

    filling: bool
    settling: bool

    @property
    def catalogue(self) -> TorrentCatalogue: ...
    @property
    def offer(self) -> Offer: ...
    @property
    def ask(self) -> Offer | None: ...
    @property
    def landed(self) -> Offer: ...
    @property
    def arriving(self) -> Callable[[list[JsonValue]], bool]: ...
    @property
    def passport(self) -> PassportOf: ...
    @property
    def playable(self) -> Playable: ...
    @property
    def workers(self) -> int: ...
    @property
    def early(self) -> bool: ...
    def publish(
        self,
        shelf: str,
        tiles: list[JsonValue],
        drops: DropCount,
        now: datetime,
        complete: bool,
        unstamped: bool = False,
    ) -> None: ...


@dataclass
class ShelfPass:
    """Заход над лентой ``rows``; публикует через кэш и отдаёт тело проверенных полок."""

    cache: _Cache
    rows: list[FeedRow]
    now: datetime
    current: dict[str, JsonValue]
    pictures: dict[str, list[Picture]] = field(default_factory=dict)
    looked: dict[str, list[JsonValue]] = field(default_factory=dict)
    shown: dict[str, list[str]] = field(default_factory=dict)
    done: dict[str, list[JsonValue]] = field(default_factory=dict)
    verdicts: dict[str, Verdict] = field(default_factory=dict)
    _joint: list[JsonValue] = field(default_factory=list)
    _fresh: int = 0
    _deadline: float = 0.0

    @property
    def early(self) -> bool:
        """Холодный заход (:func:`web.cold.cold`): показ до приговоров."""
        return self.cache.early and cold(self.current)

    def run(self) -> dict[str, JsonValue]:  # the page flags burn only for a cold pass
        self.cache.filling = self.cache.settling = self.early
        body = self._run()
        # A shelf closed empty is fetched again by the next feed attempt: the page keeps asking.
        empty = not all(self.done.get(shelf) for shelf in SHELVES)
        self.cache.filling = self.cache.settling = self.early and empty
        return body

    def _run(self) -> dict[str, JsonValue]:
        cache = self.cache
        self.pictures = {
            s: shelf_pictures(s, self.rows, cache.catalogue, self.now) for s in SHELVES
        }
        seeds = {shelf: shelf_seeds(self.pictures[shelf]) for shelf in SHELVES}
        if self.early and cache.ask is not None:
            # One ask for both shelves: the covers race once, not twice in a row.
            self._joint, self._fresh = seeds["fresh"] + seeds["popular"], len(seeds["fresh"])
            self._deadline = time.monotonic() + FILL_BY
            self._split(cache.ask(self._joint))
        else:
            self.looked = {shelf: cache.offer(seeds[shelf]) for shelf in SHELVES}
        if self.early:
            self._preview()
        shelf_judge(
            self._lanes,
            LIMIT,
            cache.playable,
            cache.workers,
            self._close,
            self._preview if self.early else lambda: None,
            self.verdicts,
            self._growing,
        )
        return {FIELD: RULE, "built_at": self.now.isoformat(), **self.done}

    def filling(self) -> bool:  # the shelves will still show more: the page keeps its counter
        waiting = [shelf for shelf in SHELVES if shelf not in self.done]
        if any(shelf not in self.shown for shelf in waiting):
            return True
        return self._growing() and any(len(self.shown[shelf]) < LIMIT for shelf in waiting)

    def _split(self, offered: list[JsonValue]) -> None:
        self.looked = {"fresh": offered[: self._fresh], "popular": offered[self._fresh :]}

    def _growing(self) -> bool:
        """Обложки ещё едут; кончились - состав полок застыл: счётчик погас, полка не растёт."""
        if self._joint and not (
            time.monotonic() < self._deadline and self.cache.arriving(self._joint)
        ):
            self._joint = []
        return bool(self._joint)

    def _lanes(self) -> list[list[tuple[str, str]]]:
        if self._joint:
            self._split(self.cache.landed(self._joint))
        return [shelf_lane(self.looked[shelf]) for shelf in SHELVES]

    def _preview(self) -> None:
        """Показать полки как есть: неизвестный приговор плитку не снимает."""
        for shelf in SHELVES:
            if shelf in self.done or not shelf_lane(self.looked[shelf]):
                continue
            offered, passport = self._offered(shelf), self.cache.passport
            tiles = shelf_tiles(self.pictures[shelf], offered, passport, self._known, LIMIT)
            keys = [str(tile.get("key")) for tile in tiles if isinstance(tile, dict)]
            if keys != self.shown.get(shelf):
                self.shown[shelf] = keys
                self.cache.publish(
                    shelf, tiles, DropCount(), self.now, complete=False, unstamped=True
                )
        self.cache.filling = self.filling()

    def _known(self, _query: str, key: str) -> Verdict:
        return self.verdicts.get(key)  # not judged yet is «unknown», and the tile stays

    def _offered(self, shelf: str) -> Offer:
        return lambda _seeds: self.looked[shelf]  # covers already asked: take the answer

    def _close(self, index: int) -> None:
        """Полке ждать больше нечего: проверенная полка, клеймо - у последней закрытой."""
        shelf = SHELVES[index]
        drops = DropCount()
        judged = drops.wrap(
            lambda query, key: (
                self.verdicts[key] if key in self.verdicts else self.cache.playable(query, key)
            )
        )
        tiles = build_shelf(
            shelf,
            self.rows,
            self.cache.catalogue,
            self._offered(shelf),
            self.cache.passport,
            judged,
            self.now,
        )
        self.done[shelf] = tiles
        last = len(self.done) == len(SHELVES)
        self.cache.publish(shelf, tiles, drops, self.now, complete=last, unstamped=self.early)
        if self.early:
            self.cache.filling = self.filling()


__all__ = ["FILL_BY", "SHELVES", "ShelfPass"]
