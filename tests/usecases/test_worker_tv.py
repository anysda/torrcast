"""Юнит без ``here`` на машине с приёмником-вкладкой и названным ТВ играет на ТВ."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from tests.fakes import composition
from tests.usecases.test_worker import KEY, _own_show, _played  # noqa: F401 - фикстура
from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.profile import CAUTIOUS
from torrcast.usecases.worker import _cmd_worker


def _raised(monkeypatch: pytest.MonkeyPatch, here: bool) -> tuple[list[str], list[tuple[str, str]]]:
    """У кого спрошен паспорт и какой приёмник поднят."""
    Path(os.environ["TORRCAST_CONFIG"]).write_text(
        json.dumps({"receiver": "browser", "tv": "living-room"})
    )
    asked: list[str] = []
    raised: list[tuple[str, str]] = []

    def detect(config: Config) -> Choice:
        asked.append(config.receiver)
        return Choice(CAUTIOUS, "паспорта нет")

    def receiver(kind: str, address: str, cert: str, profile: Any = None) -> object:
        raised.append((kind, address))
        return object()

    composition.use_profile(monkeypatch, detect)
    composition.use_receivers(monkeypatch, receiver)
    assert _cmd_worker(KEY, here, play=_played) == 0
    return asked, raised


def test_the_card_button_raises_the_tv_and_asks_its_passport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _raised(monkeypatch, False) == (["chromecast"], [("chromecast", "living-room")])


def test_the_tab_that_asked_still_plays_in_the_tab(monkeypatch: pytest.MonkeyPatch) -> None:
    """Отрицательная проба: ``here`` остаётся вкладке."""
    asked, raised = _raised(monkeypatch, True)
    assert asked == ["browser"]
    assert [kind for kind, _ in raised] == ["browser"]
