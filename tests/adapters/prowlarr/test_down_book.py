"""The book of silent indexers lives beside the state and outlives a restart."""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.prowlarr.down_book import DownBook
from torrcast.adapters.prowlarr.indexer_circle import ASK_SLACK
from torrcast.domain.circle_budget import FIRST_CIRCLE_TIMEOUT
from torrcast.domain.is_down import DOWN_AFTER, IN_TIME


def test_in_time_is_what_the_first_circle_waits_its_core() -> None:
    assert IN_TIME == FIRST_CIRCLE_TIMEOUT + ASK_SLACK


def test_the_book_outlives_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "down.json"
    book = DownBook(lambda: path, clock=lambda: 1000.0)
    for _ in range(DOWN_AFTER):
        book.hear("Knaben", answered=False)
    assert DownBook(lambda: path, clock=lambda: 1000.0).down() == {"Knaben"}
    book.hear("Knaben", answered=True)
    assert DownBook(lambda: path, clock=lambda: 1000.0).down() == frozenset()


def test_an_ask_that_outlived_its_search_tells_the_book_it_was_sent_from(tmp_path: Path) -> None:
    sent, now = tmp_path / "sent.json", tmp_path / "now.json"
    book = DownBook(lambda: now)
    for _ in range(DOWN_AFTER):
        book.hear("Knaben", answered=False, where=sent)
    assert book.down() == frozenset()
    assert DownBook(lambda: sent).down() == {"Knaben"}


def test_a_broken_book_is_an_empty_one(tmp_path: Path) -> None:
    path = tmp_path / "down.json"
    path.write_text('{"Knaben": ["x", 1]}', encoding="utf-8")
    assert DownBook(lambda: path).down() == frozenset()
