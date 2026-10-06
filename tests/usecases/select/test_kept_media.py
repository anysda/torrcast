"""Дорожки закладки по её записи: тем же путём, что ``--voice``, и без брошенной раздачи."""

from __future__ import annotations

import pytest

import torrcast.usecases.select._pick_state as _pick_state
from tests.fakes.torrent_engine import FakeTorrentEngine
from tests.usecases.select.world import entry
from torrcast.domain.config import Config
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.usecases.select.kept_media import kept_media


class _Dropped:
    """Что снесли: подделке хватает списка хэшей."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, config: Config, hashes: list[str]) -> None:
        self.calls.append(list(hashes))


def test_the_bookmark_tracks_are_read_from_its_record_and_the_torrent_is_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Карточка читает дорожки записи тем же путём, что ``--voice``, и не оставляет раздачу."""
    engine, dropped = FakeTorrentEngine(torrent_hash="e" * 40), _Dropped()
    monkeypatch.setattr(_pick_state, "_select_engines", lambda _url: engine)
    monkeypatch.setattr(_pick_state, "_select_prober", lambda url, timeout: url)
    monkeypatch.setattr("torrcast.usecases.select._voiced._release_torrents", dropped)
    saved = entry(file_idx=3)

    read: object = kept_media(Config(), saved)

    assert read == "http://fake/" + "e" * 40 + "/3", "поток - файл записи по её раздаче"
    assert engine.added == [saved.magnet] and dropped.calls == [["e" * 40]]


def test_a_silent_bookmark_torrent_is_removed_all_the_same(monkeypatch: pytest.MonkeyPatch) -> None:
    """Рой промолчал - раздача всё равно убирается, а отказ уходит карточке."""
    engine, dropped = FakeTorrentEngine(torrent_hash="f" * 40), _Dropped()

    def silent(_url: str, timeout: float) -> None:
        raise TorrcastError("no peers")

    monkeypatch.setattr(_pick_state, "_select_engines", lambda _url: engine)
    monkeypatch.setattr(_pick_state, "_select_prober", silent)
    monkeypatch.setattr("torrcast.usecases.select._voiced._release_torrents", dropped)

    with pytest.raises(TorrcastError):
        kept_media(Config(), entry())
    assert dropped.calls == [["f" * 40]]
