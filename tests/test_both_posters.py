"""Проверяет порядок двух источников картинок: второй добирает, но не подменяет."""

from __future__ import annotations

import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest

from hass import both_posters
from hass.both_posters import BothPosters
from torrcast.domain.facts.ask import Ask

WIKI = "https://upload.wikimedia.org/poster.jpg"
IMDB = "https://m.media-amazon.com/images/M/one._V1_UX500_.jpg"
PICTURE = b"\xff\xd8\xff\xe0picture"


@dataclass
class FakeSource:
    """Двойник источника: отвечает заранее известными адресами и помнит, о ком спросили."""

    known: dict[Ask, list[str]] = field(default_factory=dict)
    asked: list[list[Ask]] = field(default_factory=list)
    error: Exception | None = None

    def wanted(self, asks: Sequence[Ask], timeout: float) -> dict[Ask, list[str]]:
        self.asked.append(list(asks))
        if self.error is not None:
            raise self.error
        return {ask: self.known.get(ask, []) for ask in asks}

    def bodies(self, wanted: dict[Ask, list[str]], timeout: float) -> dict[Ask, bytes]:
        return {ask: PICTURE for ask, one in wanted.items() if one}


@dataclass
class FakeBytesClient:
    """Двойник загрузчика: отдаёт байты на любой адрес."""

    asked: list[str] = field(default_factory=list)

    def fetch(self, address: str, timeout: float) -> bytes:
        self.asked.append(address)
        return PICTURE


HERE = Ask("Матрица", 1999, "movie", "The Matrix")
THERE = Ask("Паразиты", 1999, "movie", "Les parasites")


def test_the_second_source_is_asked_only_about_those_the_first_kept_silent_about() -> None:
    """Второй источник добирает молчащих, а найденное первым не перепроверяет."""
    first = FakeSource({HERE: [WIKI]})
    second = FakeSource({THERE: [IMDB]})
    both = BothPosters(first, second, FakeBytesClient())
    assert both.wanted([HERE, THERE], 5.0) == {HERE: [WIKI], THERE: [IMDB]}
    assert second.asked == [[THERE]]


def test_the_second_source_never_overrides_the_first() -> None:
    """Обе картинки на одну картину - показывается картинка первого источника."""
    both = BothPosters(FakeSource({HERE: [WIKI]}), FakeSource({HERE: [IMDB]}), FakeBytesClient())
    assert both.wanted([HERE], 5.0) == {HERE: [WIKI]}


def test_the_first_source_answering_everyone_saves_the_second_a_walk() -> None:
    """Первый ответил всем - второго не зовут вовсе."""
    second = FakeSource()
    both = BothPosters(FakeSource({HERE: [WIKI]}), second, FakeBytesClient())
    assert both.wanted([HERE], 5.0) == {HERE: [WIKI]}
    assert second.asked == []


def test_an_urgent_row_uses_the_ready_second_source_before_a_slow_first_one() -> None:
    """Cold Wiki cannot spend the first row's two seconds while verified IMDb is ready."""
    gate = threading.Event()

    class SlowFirst(FakeSource):
        def wanted(self, asks: Sequence[Ask], timeout: float) -> dict[Ask, list[str]]:
            gate.wait(timeout)
            return super().wanted(asks, timeout)

    second = FakeSource({HERE: [IMDB]})
    both = BothPosters(SlowFirst({HERE: [WIKI]}), second, FakeBytesClient(), urgent=True)
    began = time.monotonic()
    try:
        assert both.wanted([HERE], 5.0) == {HERE: [IMDB]}
    finally:
        gate.set()
    assert time.monotonic() - began < 2.0
    assert second.asked == [[HERE]], "IMDb was kept behind the slow first source"


def test_a_broken_second_source_does_not_erase_the_answer_of_the_first() -> None:
    """🔴 Обрыв второго источника не уносит уже найденные первым картинки.

    The one it broke on stays out of the answer: unknown, to be asked again, not bare.
    """
    second = FakeSource(error=OSError("оборвалось"))
    both = BothPosters(FakeSource({HERE: [WIKI]}), second, FakeBytesClient())
    assert both.wanted([HERE, THERE], 5.0) == {HERE: [WIKI]}


def test_an_overdue_race_is_unknown_and_its_late_answer_lands_without_asking_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 The race deadline is not "no poster": the call already on the wire lands later."""
    monkeypatch.setattr(both_posters, "_URGENT_BY", 0.1)
    gate = threading.Event()

    class SlowFirst(FakeSource):
        def wanted(self, asks: Sequence[Ask], timeout: float) -> dict[Ask, list[str]]:
            self.asked.append(list(asks))
            gate.wait(timeout)
            return {ask: self.known.get(ask, []) for ask in asks}

    first, second = SlowFirst({HERE: [WIKI]}), FakeSource(error=OSError("dns"))
    both = BothPosters(first, second, FakeBytesClient(), urgent=True)
    assert both.wanted([HERE], 5.0) == {}
    landed: list[dict[Ask, list[str]]] = []
    gate.set()
    assert both.finish_urgent([HERE], 5.0, landed.append) == {HERE: [WIKI]}
    assert landed == [{HERE: [WIKI]}]
    assert first.asked == [[HERE]] and second.asked == [[HERE]], "a source was asked twice"


def test_a_quick_empty_answer_waits_for_the_other_source_before_calling_it_bare(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One source's empty answer is not the verdict while the other is still on the wire."""
    monkeypatch.setattr(both_posters, "_URGENT_BY", 0.1)
    gate = threading.Event()

    class SlowSecond(FakeSource):
        def wanted(self, asks: Sequence[Ask], timeout: float) -> dict[Ask, list[str]]:
            gate.wait(timeout)
            return super().wanted(asks, timeout)

    both = BothPosters(FakeSource(), SlowSecond({HERE: [IMDB]}), FakeBytesClient(), urgent=True)
    try:
        assert both.wanted([HERE, THERE], 5.0) == {}
    finally:
        gate.set()
    assert both.finish_urgent([HERE, THERE], 5.0, lambda _: None) == {HERE: [IMDB], THERE: []}


def test_bytes_are_taken_by_the_address_whoever_named_it() -> None:
    """Байты качаются по адресу, а чей источник его назвал - уже неважно."""
    files = FakeBytesClient()
    both = BothPosters(FakeSource(), FakeSource({THERE: [IMDB]}), files)
    assert both.bodies(both.wanted([THERE], 5.0), 5.0) == {THERE: PICTURE}
    assert files.asked == [IMDB]


def test_the_card_of_the_playing_picture_goes_the_same_two_sources() -> None:
    """Дверь карточки идёт теми же источниками: полка у неё со списком общая."""
    both = BothPosters(FakeSource(), FakeSource({THERE: [IMDB]}), FakeBytesClient())
    assert both.poster(THERE, 5.0) == PICTURE
