"""Голова показа с карточки: запись той же раздачи, настроенный профилем конфиг, хозяин."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import web.card_head
from torrcast.cli.parse_args import parse_args
from torrcast.domain.config import Config
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
    entry = object()
    monkeypatch.setattr(web.card_head, "_entry_of", lambda *_args: (entry, 0))
    config = Config()
    assert tune(config, ANDROID_TV) != config, "профиль пробы конфига не меняет: проба пуста"

    card_head(config, ANDROID_TV, "engine", _PLAN, "prep", parse_args(["кино"]))  # type: ignore[arg-type]

    assert len(wanted) == 1
    tuned, profile, engine, got, kwargs = wanted[0]
    assert tuned == tune(config, ANDROID_TV), "голова считает цель не тем конфигом, что показ"
    assert (profile, engine, got) == (ANDROID_TV, "engine", entry)
    assert kwargs == {"owner": "movie:кино:1999"}


def test_an_entry_that_does_not_build_lays_no_head(monkeypatch: pytest.MonkeyPatch) -> None:
    wanted = _heads(monkeypatch)

    def broken(*_args: object) -> Any:
        raise TorrcastError("нет файла")

    monkeypatch.setattr(web.card_head, "_entry_of", broken)

    card_head(Config(), CAUTIOUS, "engine", _PLAN, "prep", parse_args(["кино"]))  # type: ignore[arg-type]

    assert wanted == []
