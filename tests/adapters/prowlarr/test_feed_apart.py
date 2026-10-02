"""Проверяет ленту врозь: залипший индексер стоит только срока, пустой ленты срок не даёт."""

from __future__ import annotations

import threading
import time

import pytest
import requests

from torrcast.adapters.prowlarr.feed_apart import feed_apart


def _join_apart() -> None:
    """Опоздавшие дорабатывают в своих потоках: тест обязан их дождаться сам."""
    for thread in threading.enumerate():
        if thread.name.startswith("feed-apart"):
            thread.join(5)


def _row(title: str, digest: str) -> dict[str, object]:
    return {
        "title": title,
        "infoHash": digest * 40,
        "size": 1,
        "seeders": 5,
        "indexer": "idx",
        "publishDate": "2026-09-29T00:00:00Z",
    }


@pytest.mark.machine
def test_a_stuck_indexer_does_not_hold_the_ones_that_answered() -> None:
    """Молчун держит свой поток, а лента уходит к сроку с ответами остальных."""
    stop = threading.Event()

    def get(url: str) -> object:
        if url == "stuck":
            stop.wait(5)
        return [_row(f"Картина {url} 2026", url[0])]

    began = time.monotonic()
    rows = feed_apart(get, ["a", "b", "stuck"], 0.3)
    spent = time.monotonic() - began
    stop.set()
    _join_apart()

    assert spent < 1.5
    assert sorted(row.raw.title for row in rows) == ["Картина a 2026", "Картина b 2026"]
    assert rows.missed == 1  # the stuck one may still fill the shelf on the next attempt


@pytest.mark.machine
def test_nobody_in_time_waits_for_the_first_answer() -> None:
    """Никто не успел - лента не пустеет, а ждёт первого ответившего."""
    stop = threading.Event()

    def get(url: str) -> object:
        if url == "slow":
            time.sleep(0.4)
            return [_row("Поздняя 2026", "c")]
        stop.wait(5)
        return []

    rows = feed_apart(get, ["slow", "stuck"], 0.05)
    stop.set()
    _join_apart()

    assert [row.raw.title for row in rows] == ["Поздняя 2026"]
    assert rows.missed == 1


def test_all_failed_is_a_catalogue_failure() -> None:
    def get(_url: str) -> object:
        raise requests.ConnectionError("отказ")

    with pytest.raises(requests.ConnectionError):
        feed_apart(get, ["a", "b"], 1.0)
    _join_apart()


def test_a_release_seen_by_two_indexers_is_one_row() -> None:
    rows = feed_apart(lambda url: [_row(f"Раздача {url} 2026", "d")], ["a", "b"], 1.0)
    _join_apart()

    assert len(rows) == 1
    assert rows.missed == 0  # everyone answered: no fuller attempt to wait for


def test_a_failed_indexer_is_missed_too() -> None:
    def get(url: str) -> object:
        if url == "down":
            raise requests.ConnectionError("отказ")
        return [_row("Раздача 2026", "e")]

    rows = feed_apart(get, ["a", "down"], 1.0)
    _join_apart()

    assert rows.missed == 1


def _join_again() -> None:
    for thread in threading.enumerate():
        if thread.name.startswith(("feed-apart", "feed-again")):
            thread.join(5)


def test_the_re_ask_goes_only_to_the_indexer_that_refused() -> None:
    """Переспрос не трогает ответивших: отказавший спрошен снова, его строки пришли."""
    asked: list[str] = []
    down = [True]

    def get(url: str) -> object:
        asked.append(url)
        if url == "down" and down[0]:
            raise requests.ConnectionError("отказ")
        return [_row(f"Раздача {url} 2026", "d" if url == "down" else "a")]

    rows = feed_apart(get, ["a", "down"], 1.0)
    down[0] = False
    assert rows.again is not None
    more = rows.again(1.0)
    _join_again()

    assert sorted(asked) == ["a", "down", "down"]
    assert [row.raw.title for row in more] == ["Раздача down 2026"]
    assert more.missed == 0 and more.again is None


@pytest.mark.machine
def test_a_late_indexer_is_waited_for_and_not_asked_twice() -> None:
    """Опоздавший не спрашивается заново: переспрос ждёт его же ответ."""
    asked: list[str] = []
    stop = threading.Event()

    def get(url: str) -> object:
        asked.append(url)
        if url == "late":
            stop.wait(5)
        return [_row(f"Раздача {url} 2026", "f" if url == "late" else "a")]

    rows = feed_apart(get, ["a", "late"], 0.1)
    assert rows.again is not None and rows.missed == 1
    stop.set()
    more = rows.again(1.0)
    _join_again()

    assert asked.count("late") == 1
    assert [row.raw.title for row in more] == ["Раздача late 2026"]


def test_a_whole_feed_has_nothing_to_re_ask() -> None:
    rows = feed_apart(lambda url: [_row(f"Раздача {url} 2026", url[0])], ["a", "b"], 1.0)
    _join_again()

    assert rows.again is None
