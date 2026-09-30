"""Показ из вкладки: её ключ решает профиль головы и уезжает в юнит тем же доводом."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.fakes import composition
from tests.usecases.cast_command.test__cmd_play import _never, _one_film, _OnePassport
from torrcast.domain.args import Args
from torrcast.domain.choice import Choice
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.domain.profile import BROWSER, CAUTIOUS, Profile
from torrcast.usecases.cast_command._cmd_play import _cmd_play


def _played(monkeypatch: pytest.MonkeyPatch, tab: str) -> tuple[Profile, object]:
    """Профиль, которым грелась голова, и ключ, отданный юниту."""
    Path(os.environ["TORRCAST_CONFIG"]).write_text(json.dumps({"receiver": "browser"}))
    composition.use_profile(monkeypatch, lambda config: Choice(CAUTIOUS, "паспорта нет"))
    one, prep = _one_film()
    warmed: list[Profile] = []
    handed: list[object] = []

    def launch(*_args: object, **kw: object) -> int:
        handed.append(kw.get("tab"))
        return EXIT_OK

    monkeypatch.setattr("torrcast.usecases.cast_command._cmd_play._launch", launch)

    class _Bench:
        def drop_all(self) -> None:
            return None

    class _Head:
        def want(self, _config: object, profile: Profile, *_rest: object) -> None:
            warmed.append(profile)

    def choose(*_args: object, **_kw: object) -> object:
        return [one], one, prep, _Bench(), _OnePassport()

    code = _cmd_play(
        Args(query=["кино"], here=True, tab=tab),
        restart=_never,
        resume=_never,
        choose=choose,  # type: ignore[arg-type]
        head=_Head(),  # type: ignore[arg-type]
    )
    assert code == EXIT_OK
    return warmed[0], handed[0]


def test_a_measured_tab_warms_and_plays_with_its_own_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _played(monkeypatch, "chromium-linux") == (BROWSER, "chromium-linux")


@pytest.mark.parametrize("tab", ["", "webkit-ios"])
def test_a_silent_or_unmeasured_tab_warms_as_dev_did(
    monkeypatch: pytest.MonkeyPatch, tab: str
) -> None:
    """Отрицательная проба: без ключа или с незамеренным голова греется порогами ``dev``."""
    assert _played(monkeypatch, tab) == (CAUTIOUS, tab)
