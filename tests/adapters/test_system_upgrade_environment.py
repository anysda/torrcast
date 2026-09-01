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


def _fake_sudo(tmp_path: Path) -> Path:
    """Подставной sudo: записывает, как его позвали, и ничего не запускает.

    🔴 Настоящий sudo тут не годится ни при каком раскладе: он и правда поднимет права
    и запустит настоящее обновление машины, на которой идёт прогон.
    """
    calls = tmp_path / "sudo_calls.txt"
    sudo = tmp_path / "sudo"
    sudo.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{calls}"\n', encoding="utf-8")
    sudo.chmod(0o755)
    return calls


def test_without_sudo_the_rights_cannot_be_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.delenv("TORRCAST_ELEVATED", raising=False)

    assert SystemUpgradeEnvironment().can_elevate() is False


def test_a_run_already_raised_once_does_not_raise_itself_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🔴 Без этой метки sudo, который прав не дал, увёл бы обновление в бесконечную
    цепочку самоподнятий - каждое со своим приглашением пароля."""
    _fake_sudo(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("TORRCAST_ELEVATED", "1")

    assert SystemUpgradeEnvironment().can_elevate() is False


def test_the_raise_repeats_the_same_command_by_its_full_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """За sudo PATH уже не наш (`secure_path` в sudoers), поэтому команда называется
    абсолютом, а метка «нас уже поднимали» едет явным `env`: окружение sudo вытирает."""
    calls = _fake_sudo(tmp_path)
    cast = tmp_path / "cast"
    cast.write_text("#!/bin/sh\n", encoding="utf-8")
    cast.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.delenv("TORRCAST_ELEVATED", raising=False)
    monkeypatch.setattr("sys.argv", ["cast", "--upgrade"])

    environment = SystemUpgradeEnvironment()

    assert environment.can_elevate() is True
    assert environment.elevate() == 0
    assert calls.read_text(encoding="utf-8").strip() == (
        f"-- env TORRCAST_ELEVATED=1 {cast} --upgrade"
    )
