"""CLI без ``here`` на машине с приёмником-вкладкой и названным ТВ готовит показ для ТВ."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.fakes import composition
from tests.usecases.cast_command.test__cmd_play import _never, _one_film, _OnePassport
from torrcast.domain.args import Args
from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.domain.profile import CAUTIOUS
from torrcast.usecases.cast_command._cmd_play import _cmd_play


def _launched(monkeypatch: pytest.MonkeyPatch, here: bool) -> tuple[list[str], list[str]]:
    """У кого спрошен паспорт и с каким приёмником ушёл запуск."""
    Path(os.environ["TORRCAST_CONFIG"]).write_text(
        json.dumps({"receiver": "browser", "tv": "living-room"})
    )
    asked: list[str] = []
    launched: list[str] = []

    def detect(config: Config) -> Choice:
        asked.append(config.receiver)
        return Choice(CAUTIOUS, "паспорта нет")

    composition.use_profile(monkeypatch, detect)
    one, prep = _one_film()

    def launch(config: Config, *_args: object, **_kw: object) -> int:
        launched.append(config.receiver)
        return EXIT_OK

    monkeypatch.setattr("torrcast.usecases.cast_command._cmd_play._launch", launch)

    class _Bench:
        def drop_all(self) -> None:
            return None

    class _Head:
        def want(self, *_rest: object) -> None:
            return None

    def choose(*_args: object, **_kw: object) -> object:
        return [one], one, prep, _Bench(), _OnePassport()

    code = _cmd_play(
        Args(query=["кино"], here=here),
        restart=_never,
        resume=_never,
        choose=choose,  # type: ignore[arg-type]
        head=_Head(),  # type: ignore[arg-type]
    )
    assert code == EXIT_OK
    return asked, launched


def test_the_card_button_is_prepared_for_the_tv(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _launched(monkeypatch, False) == (["chromecast"], ["chromecast"])


def test_the_tab_that_asked_is_prepared_for_the_tab(monkeypatch: pytest.MonkeyPatch) -> None:
    """Отрицательная проба: ``here`` остаётся вкладке."""
    assert _launched(monkeypatch, True) == (["browser"], ["browser"])
