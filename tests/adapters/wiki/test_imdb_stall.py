"""Заглохшее соединение подсказчика IMDb не держит картину до срока (:mod:`imdb_poster`).

Из домашней сети соединение с подсказчиком глохло насовсем на восьмом запросе: ответ не
приходил, и ряд ждал срок подсказчика 4 с, хотя сервер отвечает за десятые доли секунды.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from torrcast.adapters.wiki import imdb_poster
from torrcast.adapters.wiki.imdb_poster import _ASK_TIMEOUT, _FIRST_TRY, ImdbPoster
from torrcast.domain.facts.ask import Ask

RAW = "https://m.media-amazon.com/images/M/MV5BNWI5OTEzMzE@._V1_.jpg"
ASK = Ask("Паразиты", 1999, "movie", "Les parasites")
ROW = {"id": "tt0233258", "l": "Les parasites", "y": 1999, "qid": "movie", "i": {"imageUrl": RAW}}


@dataclass
class _Stalling:
    """Подсказчик, чьи первые ``stalls`` ответов глохнут на весь срок; помнит сроки запросов."""

    stalls: int
    waits: list[float] = field(default_factory=list)
    now: float = 0.0

    def clock(self) -> float:
        return self.now

    def warm(self, host: str) -> None:
        pass

    def get(
        self,
        host: str,
        path: str,
        params: dict[str, str],
        headers: dict[str, str],
        timeout: float,
        foreground: bool = False,
    ) -> Any:
        self.waits.append(timeout)
        if len(self.waits) <= self.stalls:
            self.now += timeout
            raise TimeoutError("The read operation timed out")
        return {"d": [ROW]}


class _NoBytes:
    def fetch(self, address: str, timeout: float) -> bytes:
        return b""


def test_a_stalled_lookup_is_asked_again_long_before_the_source_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Молчание первой попытки обрывается за :data:`_FIRST_TRY`, вторая идёт сразу."""
    client = _Stalling(stalls=1)
    monkeypatch.setattr(imdb_poster, "monotonic", client.clock)
    found = ImdbPoster(client, _NoBytes()).wanted([ASK], 5.0)
    assert ASK in found, "заглохший запрос оставил картину без обложки"
    assert client.waits[0] <= _FIRST_TRY < _ASK_TIMEOUT, client.waits
    assert len(client.waits) == 2
    assert client.waits[1] == _ASK_TIMEOUT - _FIRST_TRY, "повтор начал свой срок заново"


def test_a_source_silent_twice_leaves_the_picture_unknown() -> None:
    """Повтор один: второе молчание - отказ источника, картина остаётся неизвестной."""
    client = _Stalling(stalls=2)
    assert ImdbPoster(client, _NoBytes()).wanted([ASK], 5.0) == {}
    assert len(client.waits) == 2


def test_a_short_budget_is_not_split_in_two() -> None:
    """Срок короче первой попытки - одна попытка во весь срок, без повтора."""
    client = _Stalling(stalls=1)
    assert ImdbPoster(client, _NoBytes()).wanted([ASK], 0.5) == {}
    assert client.waits == [0.5]
