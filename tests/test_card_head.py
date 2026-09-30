"""Голова показа с карточки: запись той же раздачи, настроенный профилем конфиг, хозяин."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import web.card_head
from torrcast.cli.parse_args import parse_args
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.profile import ANDROID_TV, CAUTIOUS
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.domain.tune import tune
from web.card_head import card_head

_PLAN: Any = SimpleNamespace(picture=SimpleNamespace(key="movie:кино:1999"))


def _heads(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    wanted: list[tuple[Any, ...]] = []

    def want(*args: Any, **kwargs: Any) -> None:
        wanted.append((*args, kwargs))

    monkeypatch.setattr(web.card_head, "HEAD", SimpleNamespace(want=want))
    return wanted


def test_the_card_head_is_the_entry_of_its_pick_owned_by_the_picture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wanted = _heads(monkeypatch)
    entry = Entry("кино", "magnet:?xt=urn:btih:cc")
    monkeypatch.setattr(web.card_head, "_entry_of", lambda *_args: (entry, 0))
    config = Config()
    assert tune(config, ANDROID_TV) != config, "профиль пробы конфига не меняет: проба пуста"

    card_head(config, ANDROID_TV, "engine", _PLAN, "prep", parse_args(["кино"]))  # type: ignore[arg-type]

    assert len(wanted) == 1
    tuned, profile, engine, got, kwargs = wanted[0]
    assert tuned == tune(config, ANDROID_TV), "голова считает цель не тем конфигом, что показ"
    assert (profile, engine, got) == (ANDROID_TV, "engine", entry)
    assert kwargs["owner"] == "movie:кино:1999"
    assert callable(kwargs["late"])


def test_an_entry_that_does_not_build_lays_no_head(monkeypatch: pytest.MonkeyPatch) -> None:
    wanted = _heads(monkeypatch)

    def broken(*_args: object) -> Any:
        raise TorrcastError("нет файла")

    monkeypatch.setattr(web.card_head, "_entry_of", broken)

    card_head(Config(), CAUTIOUS, "engine", _PLAN, "prep", parse_args(["кино"]))  # type: ignore[arg-type]

    assert wanted == []


def test_a_bookmark_card_lays_the_bookmark_entry_as_the_show_gets_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Голова закладки - её запись как есть: тот же ключ полки, что у показа с места."""
    wanted = _heads(monkeypatch)

    def picked(*_args: object) -> Any:
        return pytest.fail("the circle's pick is not what «Play» resumes")

    monkeypatch.setattr(web.card_head, "_entry_of", picked)
    kept = Entry("Тачки", "magnet:?xt=urn:btih:aa", pos=2955.0, dur=6960.0, audio=2)

    card_head(Config(), ANDROID_TV, "engine", _PLAN, "prep", parse_args(["cars"]), kept)  # type: ignore[arg-type]

    assert len(wanted) == 1
    tuned, profile, _engine, got, kwargs = wanted[0]
    assert (tuned, profile, got) == (tune(Config(), ANDROID_TV), ANDROID_TV, kept)
    assert kwargs["owner"] == "movie:кино:1999"
    assert callable(kwargs["late"])


@pytest.mark.parametrize(
    ("live", "late"),
    [("magnet:?xt=urn:btih:aa", True), ("magnet:?xt=urn:btih:bb", False), (None, False)],
    ids=["same", "other", "none"],
)
def test_the_card_head_is_late_once_the_show_of_its_torrent_is_up(
    monkeypatch: pytest.MonkeyPatch, live: str | None, late: bool
) -> None:
    """Юнит уже поднял эту раздачу: голову карточки класть поздно, чужой показ не мешает."""
    wanted = _heads(monkeypatch)
    showing = None if live is None else ("movie:x", Entry("x", live))
    state = SimpleNamespace(showing=lambda: showing)
    monkeypatch.setattr(web.card_head, "watch_store", lambda: SimpleNamespace(load=lambda: state))
    kept = Entry("Тачки", "magnet:?xt=urn:btih:AA", pos=2955.0, dur=6960.0)

    card_head(Config(), CAUTIOUS, "engine", _PLAN, "prep", parse_args(["cars"]), kept)  # type: ignore[arg-type]

    assert wanted[0][-1]["late"]() is late
