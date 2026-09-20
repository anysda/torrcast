"""Идёт ли каст на телевизор прямо сейчас: один ответ для шапки, ящика и карточки."""

from __future__ import annotations

import pytest

from tests.fakes.receiver import FakeReceiver
from tests.fakes.state_store import FakeStateStore
from torrcast.domain.entry import Entry
from torrcast.domain.position import Position
from torrcast.ports.state_store import slot as state_slot
from web.tv_live import tv_live
from web.tv_session import SESSION


def _showing() -> None:
    """Поставить идущий показ: непустой ``torrent`` - и есть весь признак показа."""
    fake = FakeStateStore()
    state = fake.load()
    state.entries["movie:matrix:1999"] = Entry(
        "Matrix", "magnet:matrix", kind="movie", pos=340.7, dur=8175.0, torrent="abc"
    )
    fake.save(state)
    state_slot.install(fake)


def test_a_show_running_in_the_tab_itself_is_no_cast_to_the_tv() -> None:
    """Главный случай правки: вкладка играет сама, телевизора в этом показе нет вовсе.

    Признак показа (``showing``) места не знает, и экраны брали его за занятый приёмник.
    """
    _showing()

    assert tv_live({"url": "http://x/out.m3u8", "title": "Matrix", "key": "k1"}) is False


def test_a_show_raised_straight_on_the_tv_and_still_running_is_a_cast() -> None:
    """Ящик написал ``tv: true`` (приёмник не вкладка), и показу есть на что опереться."""
    _showing()

    assert tv_live({"title": "Matrix", "key": "k1", "tv": True}) is True


def test_the_boxs_own_word_is_worth_nothing_without_a_live_show() -> None:
    """Раз написанное ``tv: true`` переживает снятый показ навсегда: веры ему нет."""
    state_slot.install(FakeStateStore())

    assert tv_live({"title": "Matrix", "key": "k1", "tv": True}) is False


def test_a_cast_carried_out_of_the_tab_by_hand_is_a_cast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """«На ТВ» из вкладки: ящик про ТВ не знает, каст держит :mod:`web.tv_session`."""
    tv = FakeReceiver(Position(0.0, 0.0))
    monkeypatch.setattr(SESSION, "factory", lambda address, profile: tv)
    monkeypatch.setattr(SESSION, "poll_seconds", 0.01)
    monkeypatch.setattr(SESSION, "_receiver", None)
    state_slot.install(FakeStateStore())
    SESSION.start("10.0.0.50", "Matrix", "http://x/out.m3u8", 12.0, key="k1")

    try:
        assert tv_live({"title": "Matrix", "key": "k1"}) is True
    finally:
        SESSION.stop()
