"""The book of silent indexers lives beside the state and outlives a restart."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from torrcast.adapters.filesystem.state import write_atomic
from torrcast.adapters.prowlarr import circle_wait as circle_wait_module
from torrcast.adapters.prowlarr.circle_wait import circle_wait
from torrcast.adapters.prowlarr.down_book import DownBook
from torrcast.adapters.prowlarr.spawn_ask import _Ask


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


@pytest.mark.machine
def test_a_circle_tells_its_silence_without_waiting_for_the_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One fsync on the stand took 3.85 s, and the circle that told the book waited it."""
    monkeypatch.setattr(circle_wait_module, "IN_TIME", 0.0)
    monkeypatch.setattr(write_atomic.os, "fsync", lambda _fd: time.sleep(1.0))
    book = DownBook(lambda: tmp_path / "down.json")
    began = time.monotonic()
    circle_wait([_Ask("Knaben", 0.2)], names=False, began=began, slack=0.0, book=book)
    elapsed = time.monotonic() - began
    assert elapsed < 0.5, f"the circle of 0.2 s ended at {elapsed:.2f} s"
    assert (tmp_path / "down.json").exists(), "the silence is still told"


@pytest.mark.machine
def test_the_book_is_read_while_a_silence_is_written(tmp_path: Path) -> None:
    """A circle starts by reading the book: it waited the lock of a write up to 0.38 s."""
    book = DownBook(lambda: tmp_path / "down.json")
    read: list[float] = []
    reader = threading.Thread(target=lambda: (book.down(), read.append(time.monotonic())))
    with book._lock:
        began = time.monotonic()
        reader.start()
        reader.join(1.0)
    assert read, "the book was not read while a silence was written"
    assert read[0] - began < 0.1, f"the book was read in {read[0] - began:.2f} s"
