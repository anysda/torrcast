"""Собранная команда обновления доводит сценарий до экрана целиком.

Спрашивается связка, а не сценарий: язык берётся из настройки человека, а живой показ
виден команде до всякой работы. Самой установки собранная команда не делает - её делает
загрузчик, - но и молчать в его отсутствие она не вправе.

Корень тут ставится настоящий: в бою команда всегда идёт после
:func:`torrcast.runtime.wire.wire`, и держатель языка кладёт именно он.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakes.show_unit import FakeShowUnit
from torrcast.adapters.filesystem.state.save_config import save_config
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.config import Config
from torrcast.domain.exit_codes import EXIT_INFRA
from torrcast.runtime.upgrade_command import upgrade_command
from torrcast.runtime.wire import wire


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "config.json"))
    monkeypatch.setenv("TORRCAST_PREFIX", str(tmp_path / "prefix"))


def test_the_refusal_speaks_the_remembered_tongue(
    show_unit: FakeShowUnit, capsys: pytest.CaptureFixture[str]
) -> None:
    """Обновление разговаривает на языке настройки, как установщик и ``cast --help``."""
    save_config(Config(tv="10.0.0.2", language="ru"))
    wire()
    show_unit.alive = False

    assert upgrade_command() == EXIT_INFRA
    assert phrase("upgrade.needs_root") in capsys.readouterr().out


def test_a_running_show_stops_the_upgrade_before_anything_is_touched(
    show_unit: FakeShowUnit, capsys: pytest.CaptureFixture[str]
) -> None:
    """Корень тут не зовётся нарочно: он заполнил бы слот юнита настоящим systemd, и
    показ, которого проверка боится, стенду было бы негде показать.
    """
    save_config(Config(tv="10.0.0.2", language="en"))
    show_unit.alive = True
    show_unit.playing = "movie:муха"

    assert upgrade_command() == EXIT_INFRA
    said = capsys.readouterr().out
    assert "cast stop" in said
    assert phrase("upgrade.needs_root") not in said
