"""Живое окружение обновления: где лежит загрузчик и чем он запускается.

🔴 Главная проверка тут одна - загрузчик запускается КОПИЕЙ. Установка переписывает
``/opt/torrcast`` под работающим процессом, и ``sh``, дочитывающий подменённый под собой
файл, уехал бы в середину чужого текста. Промах молчаливый: на целом дереве оригинал и
копия ведут себя одинаково, и разойдутся они ровно в тот раз, когда обновление настоящее.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from torrcast.adapters.system_upgrade_environment import SystemUpgradeEnvironment


def test_a_missing_loader_is_an_empty_answer_not_a_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TORRCAST_PREFIX", str(tmp_path))

    assert SystemUpgradeEnvironment().loader() == ""


def test_the_installed_loader_is_named_by_its_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "install").write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("TORRCAST_PREFIX", str(tmp_path))

    assert SystemUpgradeEnvironment().loader() == str(tmp_path / "install")


def test_root_is_answered_by_the_process_itself() -> None:
    assert SystemUpgradeEnvironment().is_root() == (os.geteuid() == 0)


def test_the_loader_runs_as_a_copy_and_hears_the_version_and_the_tongue(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    loader = tmp_path / "install"
    loader.write_text(
        '#!/bin/sh\necho "ran $0 from $TORRCAST_UPGRADE_FROM in $TORRCAST_LANGUAGE"\n',
        encoding="utf-8",
    )

    code = SystemUpgradeEnvironment().hand_off(str(loader), "1.0.0", "ru")

    said = capfd.readouterr().out
    assert code == 0
    assert "from 1.0.0 in ru" in said
    ran = said.split("ran ", 1)[1].split(" from", 1)[0]
    assert ran != str(loader), "загрузчик запущен оригиналом - установка перепишет его под sh"
    assert Path(ran).name == "install"


def test_the_loaders_own_code_comes_back_undressed(tmp_path: Path) -> None:
    loader = tmp_path / "install"
    loader.write_text("#!/bin/sh\nexit 3\n", encoding="utf-8")

    assert SystemUpgradeEnvironment().hand_off(str(loader), "1.0.0", "en") == 3


def test_the_temporary_copy_does_not_outlive_the_run(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    loader = tmp_path / "install"
    loader.write_text('#!/bin/sh\necho "$0"\n', encoding="utf-8")

    SystemUpgradeEnvironment().hand_off(str(loader), "1.0.0", "en")

    left = Path(capfd.readouterr().out.strip())
    assert not left.exists() and not left.parent.exists()
