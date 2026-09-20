"""Идёт ли ИМЕННО эта картина на телевизоре: признак кнопок карточки."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakes.show_unit import FakeShowUnit
from tests.fakes.state_store import FakeStateStore
from torrcast.adapters.browser.write_web_box import write_web_box
from torrcast.domain.entry import Entry
from torrcast.ports.state_store import slot as state_slot
from web.playing_on_tv import playing_on_tv

_KEY = "movie:matrix:1999"


def _showing(key: str = _KEY) -> None:
    """Поставить идущий показ картины ``key``: показом его делает непустой ``torrent``."""
    fake = FakeStateStore()
    state = fake.load()
    state.entries[key] = Entry(
        "Matrix", "magnet:matrix", kind="movie", pos=340.7, dur=8175.0, torrent="abc"
    )
    fake.save(state)
    state_slot.install(fake)


def test_a_picture_playing_in_the_tab_itself_does_not_lock_the_card(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, show_unit: FakeShowUnit
) -> None:
    """Показ идёт во вкладке, телевизора у него нет: подключаться зрителю не к чему.

    Карточка ставила такой картине «Подключиться»/«Завершить» вместо «Играть» - надписи
    приёмника на машине, где каста нет вовсе.
    """
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    write_web_box(tmp_path, url="http://x/out.m3u8", title="Matrix", at=340.7, key="k1")
    show_unit.alive = True
    _showing()

    assert playing_on_tv(_KEY) is False


def test_a_picture_playing_on_the_tv_marks_the_card_playing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, show_unit: FakeShowUnit
) -> None:
    """TC-1225: к показу на телевизоре зрителю есть куда подключиться."""
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    write_web_box(tmp_path, url="http://x/out.m3u8", title="Matrix", at=340.7, key="k1", tv=True)
    show_unit.alive = True
    _showing()

    assert playing_on_tv(_KEY) is True


def test_another_picture_on_the_tv_is_not_this_cards_show(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, show_unit: FakeShowUnit
) -> None:
    """На ТВ идёт другое кино: эта карточка живёт обычным набором кнопок."""
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    write_web_box(tmp_path, url="http://x/out.m3u8", title="Matrix", at=340.7, key="k1", tv=True)
    show_unit.alive = True
    _showing()

    assert playing_on_tv("movie:dune:2021") is False


def test_a_hash_left_by_a_failed_drop_without_a_live_unit_is_not_a_show(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Снос раздачи не дошёл до службы: хэш в записи есть, юнита нет - показа нет."""
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    write_web_box(tmp_path, url="http://x/out.m3u8", title="Matrix", at=340.7, key="k1", tv=True)
    _showing()

    assert playing_on_tv(_KEY) is False
