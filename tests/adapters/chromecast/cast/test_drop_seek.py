"""Закрытие перемотки, кончившейся ничем: записью, а не молчанием."""

from __future__ import annotations

from typing import Any

import pytest

from tests.adapters.chromecast.cast.wired import Wired
from torrcast.adapters.chromecast.cast.drop_seek import _drop_seek
from torrcast.adapters.filesystem.trace_journal.writer import _Writer


@pytest.fixture
def queued(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(_Writer, "put", lambda _self, record: seen.append(record))
    return seen


def test_a_seek_that_never_showed_a_picture_is_written_down(
    queued: list[dict[str, Any]],
) -> None:
    """«Нет строки в ленте» пришлось бы читать как «перемотки не было», а она была.

    Ждать сдвига указателя вечно нельзя: сессия обрывается, сторож перебивает прыжок
    нуджем, человек мотает второй раз. Кончившаяся ничем перемотка - это и есть худший
    исход, ради которого метрику заводили.
    """
    receiver = Wired()
    receiver._seek_from, receiver._seek_to, receiver._seek_since = 100.0, 900.0, 5.0

    _drop_seek(receiver, "сессия оборвалась")

    assert [(rec["event"], rec["wait"], rec["why"]) for rec in queued] == [
        ("seek", None, "сессия оборвалась")
    ]
    assert receiver._seek_since == 0.0, "перемотка закрыта - второй раз о ней не пишем"


def test_there_is_nothing_to_close_when_no_seek_is_open(queued: list[dict[str, Any]]) -> None:
    """Открытой перемотки нет - и записи быть не должно: лента не место для пустых строк."""
    receiver = Wired()

    _drop_seek(receiver, "сессия оборвалась")

    assert queued == []
