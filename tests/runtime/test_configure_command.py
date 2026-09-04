"""Собранная команда настройки ТВ пишет адрес в конфиг и говорит, что записала."""

import json
from pathlib import Path

import pytest

from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.domain.catalogs.phrase import phrase
from torrcast.runtime.configure_command import configure_command


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "config.json"))


@pytest.fixture(autouse=True)
def _russian_setup(_russian_product: None) -> None:
    """Предмет всего модуля - настройка ТВ, писанная по-русски до языкового яруса."""


def test_a_named_address_is_saved_as_is(capsys: pytest.CaptureFixture[str]) -> None:
    assert configure_command("10.0.0.50") == 0
    assert (load_config().tv, load_config().receiver) == ("10.0.0.50", "chromecast")
    line = phrase("configure.tv_line", name="", address="10.0.0.50", note="")
    assert capsys.readouterr().out.strip() == line


def test_the_mock_address_switches_the_receiver(capsys: pytest.CaptureFixture[str]) -> None:
    assert configure_command("mock") == 0
    assert (load_config().tv, load_config().receiver) == ("mock", "mock")
    assert phrase("configure.headless_note") in capsys.readouterr().out


def test_the_rest_of_the_configuration_survives_the_write(tmp_path: Path) -> None:
    """Запись адреса не трогает ключи, которых сценарий настройки не знает.

    🔴 Проба идёт по ЗАСЕЯННОМУ файлу. Прежняя спрашивала, есть ли в файле
    ``hls_readrate`` после записи в пустоту, и не отличала «ключ уцелел» от «запись
    вморозила в файл умолчание, которого человек не называл» (TC-669): зеленела на
    обоих. Засеянный файл различает их - чужое значение обязано остаться СВОИМ.
    """
    foreign = {"token": "7788:AAF-боевой-токен", "hls_readrate": 1.5}
    (tmp_path / "config.json").write_text(json.dumps(foreign), encoding="utf-8")

    configure_command("10.0.0.50")
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))

    assert saved["tv"] == "10.0.0.50"
    assert {name: saved.get(name) for name in foreign} == foreign, (
        "запись адреса стёрла или переписала ключи, которых сценарий не знает"
    )
