"""Схема ``play/resupply``: раздачу вернули магнитом, и вернулась ли она под тем же хэшем."""

from __future__ import annotations

import pytest

from tests.adapters.filesystem.trace_journal.tape import caught
from torrcast.adapters.filesystem.trace_journal.resupply import resupply


def test_the_record_names_our_torrent_and_whether_it_came_back_the_same(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Хэш и исход: событие про трекеры, и без хэша по нему не видно, чью раздачу чинили.

    URL потока несёт только хэш, и служба, пережившая перезапуск, заводит по нему раздачу
    без трекеров - ноль байт при живом рое. Вернулась ли она тем же хэшем, и есть весь
    смысл записи.
    """
    seen = caught(monkeypatch)

    resupply("0123456789abcdef", ok=False)

    assert seen == [("play", "resupply", {"torrent": "0123456789abcdef", "ok": False})]
