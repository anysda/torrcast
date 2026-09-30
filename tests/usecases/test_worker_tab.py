"""Юнит показа судит вкладку тем же ключом, что CLI: замеренной - её пороги, прочим - ``dev``."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from tests.fakes import composition
from tests.usecases.test_worker import KEY, _own_show, _played  # noqa: F401 - фикстура
from torrcast.domain.choice import Choice
from torrcast.domain.profile import BROWSER, CAUTIOUS, Profile
from torrcast.usecases.worker import _cmd_worker


def _profile_of(monkeypatch: pytest.MonkeyPatch, tab: str) -> Profile:
    """Профиль, с которым юнит поднял приёмник вкладки под ключом ``tab``."""
    Path(os.environ["TORRCAST_CONFIG"]).write_text(json.dumps({"receiver": "browser"}))
    composition.use_profile(monkeypatch, lambda config: Choice(CAUTIOUS, "паспорта нет"))
    given: list[Profile] = []

    def receiver(kind: str, address: str, cert: str, profile: Any = None) -> object:
        given.append(profile)
        return object()

    composition.use_receivers(monkeypatch, receiver)
    assert _cmd_worker(KEY, True, tab, play=_played) == 0
    return given[0]


def test_a_measured_tab_is_played_with_its_own_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _profile_of(monkeypatch, "gecko-linux") is BROWSER


@pytest.mark.parametrize("tab", ["", "webkit-ios", "chromium-android", "chromium-linux-bare"])
def test_any_other_tab_is_played_as_dev_played_it(
    monkeypatch: pytest.MonkeyPatch, tab: str
) -> None:
    """Отрицательная проба: без ключа или с незамеренным - осторожный, ровно как ``dev``."""
    assert _profile_of(monkeypatch, tab) is CAUTIOUS
