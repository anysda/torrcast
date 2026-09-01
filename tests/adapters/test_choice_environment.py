"""Проверяет системное окружение выбора."""

from pathlib import Path

import pytest

from torrcast.adapters.choice_environment import environment


def test_choice_environment_has_terminal_width() -> None:
    """Ширина терминала всегда положительна."""
    assert environment.columns() > 0


def test_external_show_reads_the_telegram_control_without_inherited_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Консольный показ не наследует процесс бота, но пульт у них один."""
    control = tmp_path / "torrcast-telegram-0.ctl"
    control.write_text("toggle", encoding="utf-8")
    monkeypatch.delenv(environment.ctl_env, raising=False)
    monkeypatch.setattr("torrcast.adapters.choice_environment.os.getuid", lambda: 0)
    monkeypatch.setattr("torrcast.adapters.choice_environment.Path", lambda _name: control)

    assert environment.read_command() == "toggle"
    assert not control.exists(), "одноразовая команда съедена"
