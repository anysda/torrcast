"""Собранная команда настройки ТВ пишет адрес в конфиг и говорит, что записала."""

from pathlib import Path

import pytest

from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.runtime.configure_command import configure_command


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "config.json"))


def test_a_named_address_is_saved_as_is(capsys: pytest.CaptureFixture[str]) -> None:
    assert configure_command("10.0.0.50") == 0
    assert (load_config().tv, load_config().receiver) == ("10.0.0.50", "chromecast")
    assert capsys.readouterr().out.strip() == "ТВ: 10.0.0.50"


def test_the_mock_address_switches_the_receiver(capsys: pytest.CaptureFixture[str]) -> None:
    assert configure_command("mock") == 0
    assert (load_config().tv, load_config().receiver) == ("mock", "mock")
    assert "headless-приёмник" in capsys.readouterr().out


def test_the_rest_of_the_configuration_survives_the_write(tmp_path: Path) -> None:
    configure_command("10.0.0.50")
    saved = (tmp_path / "config.json").read_text(encoding="utf-8")

    assert "hls_readrate" in saved, "конфиг пишется целиком, а не одним срезом сценария"
