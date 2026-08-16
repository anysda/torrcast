"""Собранная команда остановки доводит сценарий до экрана целиком."""

from pathlib import Path

import pytest

from torrcast import commands
from torrcast.runtime.stop_command import stop_command


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "config.json"))


def test_a_dead_unit_is_reported_as_silence(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(commands, "unit_active", lambda: False)
    monkeypatch.setattr(commands, "unit_key", lambda: "")
    monkeypatch.setattr(commands, "stop_play_unit", lambda: None)

    assert stop_command() == 0
    assert capsys.readouterr().out.strip() == "ничего не играет"


def test_the_stopped_show_is_named_with_its_position(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from torrcast.state import Entry, State

    state = State()
    state.put("movie:моана-2", Entry(title="Моана 2", magnet="magnet:?x=1", pos=660.0, dur=5978.0))
    state.save()
    monkeypatch.setattr(commands, "unit_active", lambda: True)
    monkeypatch.setattr(commands, "unit_key", lambda: "movie:моана-2")
    monkeypatch.setattr(commands, "stop_play_unit", lambda: None)

    assert stop_command() == 0
    assert "остановлено: «Моана 2» на 0:11:00 / 1:39:38" in capsys.readouterr().out
