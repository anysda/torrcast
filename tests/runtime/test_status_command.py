"""Собранная команда состояния читает конфиг один раз и говорит о показе словами."""

from pathlib import Path

import pytest

from tests.fakes.show_unit import FakeShowUnit
from torrcast.domain.catalogs.phrase import phrase
from torrcast.runtime.status_command import status_command


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "config.json"))


def test_nothing_plays_and_nothing_was_watched(
    show_unit: FakeShowUnit, capsys: pytest.CaptureFixture[str]
) -> None:
    show_unit.alive = False

    assert status_command() == 0
    assert capsys.readouterr().out.strip() == phrase("status.nothing_playing")


def test_the_configuration_is_read_once_for_the_whole_answer(
    show_unit: FakeShowUnit, capsys: pytest.CaptureFixture[str]
) -> None:
    from torrcast.adapters.filesystem.state.load_config import load_config
    from torrcast.adapters.filesystem.state.state import State
    from torrcast.domain.config import Config
    from torrcast.domain.entry import Entry

    state = State()
    state.put("movie:моана-2", Entry(title="Моана 2", magnet="magnet:?x=1", pos=600.0, dur=7200.0))
    state.save()
    reads: list[int] = []

    def counted() -> Config:
        reads.append(1)
        return load_config()

    show_unit.alive = True
    show_unit.playing = "movie:моана-2"
    assert status_command(counted) == 0
    assert reads == [1], "конфиг у команды один на все три вопроса сеанса"
    line = phrase("status.playing", what="«Моана 2»", pos="0:10:00", duration="2:00:00")
    assert line in capsys.readouterr().out
