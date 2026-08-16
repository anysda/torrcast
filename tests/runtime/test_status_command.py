"""Собранная команда состояния читает конфиг один раз и говорит о показе словами."""

from pathlib import Path

import pytest

from torrcast import commands
from torrcast.runtime.status_command import status_command


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "config.json"))


def test_nothing_plays_and_nothing_was_watched(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(commands, "unit_active", lambda: False)

    assert status_command() == 0
    assert capsys.readouterr().out.strip() == "ничего не играет"


def test_the_configuration_is_read_once_for_the_whole_answer(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from torrcast.state import Entry, State, load_config

    state = State()
    state.put("movie:моана-2", Entry(title="Моана 2", magnet="magnet:?x=1", pos=600.0, dur=7200.0))
    state.save()
    reads: list[int] = []

    def counted() -> object:
        reads.append(1)
        return load_config()

    monkeypatch.setattr(commands, "unit_active", lambda: True)
    monkeypatch.setattr(commands, "unit_key", lambda: "movie:моана-2")
    monkeypatch.setattr(commands, "load_config", counted)

    assert status_command() == 0
    assert reads == [1], "конфиг у команды один на все три вопроса сеанса"
    assert "играю «Моана 2» - 0:10:00 / 2:00:00" in capsys.readouterr().out
