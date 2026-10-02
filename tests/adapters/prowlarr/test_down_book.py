"""The book of silent indexers lives beside the state and outlives a restart."""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.prowlarr.down_book import DownBook


def test_the_book_outlives_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "down.json"
    book = DownBook(lambda: path, clock=lambda: 1000.0)
    for _ in range(3):
        book.hear("Knaben", answered=False)
    assert DownBook(lambda: path, clock=lambda: 1000.0).down() == {"Knaben"}
    book.hear("Knaben", answered=True)
    assert DownBook(lambda: path, clock=lambda: 1000.0).down() == frozenset()


def test_an_ask_that_outlived_its_search_tells_the_book_it_was_sent_from(tmp_path: Path) -> None:
    sent, now = tmp_path / "sent.json", tmp_path / "now.json"
    book = DownBook(lambda: now)
    for _ in range(3):
        book.hear("Knaben", answered=False, where=sent)
    assert book.down() == frozenset()
    assert DownBook(lambda: sent).down() == {"Knaben"}


def test_a_broken_book_is_an_empty_one(tmp_path: Path) -> None:
    path = tmp_path / "down.json"
    path.write_text('{"Knaben": ["x", 1]}', encoding="utf-8")
    assert DownBook(lambda: path).down() == frozenset()
