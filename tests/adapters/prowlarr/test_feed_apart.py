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
