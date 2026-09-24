"""Проверяет область юнита и то, что вызов systemd не роняет команду на чужой беде."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from torrcast.adapters.systemd import _systemd_call
from torrcast.adapters.systemd.unit_active import unit_active
from torrcast.adapters.systemd.unit_why import unit_why


def test_the_scope_is_the_user_one_unless_we_are_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """Постоянных юнитов нет ни там, ни там, но область у transient обязана совпадать.

    Промахнись область - и ``systemctl stop`` гасит пустоту, а ``status`` докладывает,
    что показа нет, пока показ идёт.
    """
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    assert _systemd_call._scope() == []
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    assert _systemd_call._scope() == ["--user"]


def test_the_call_carries_the_scope_and_never_raises_on_a_bad_return_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Область уходит первым аргументом, а ненулевой код разбирает зовущий, а не исключение.

    Отсутствие юнита - обычный ответ ``systemctl``, и падать на нём команде нельзя:
    ``cast stop`` без показа обязан молча кончиться.
    """
    seen: list[tuple[list[str], dict[str, Any]]] = []

    def remember(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.append((command, kwargs))
        return subprocess.CompletedProcess(command, 5, "", "нет такого юнита")

    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.setattr(subprocess, "run", remember)
    done = _systemd_call._systemd("systemctl", "stop", "torrcast-play")

    assert done.returncode == 5, "ненулевой код обязан доехать до зовущего"
    command, kwargs = seen[-1]
    assert command == ["systemctl", "--user", "stop", "torrcast-play"]
    assert kwargs["check"] is False, "чужой код возврата не наша авария"
    assert kwargs["text"] is True and kwargs["capture_output"] is True
    assert kwargs["timeout"] > 0, "без потолка повисший systemctl вешает команду навсегда"


def test_the_plumbing_answers_about_a_unit_that_does_not_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Разговор с командами тут настоящий, а менеджер служб принадлежит тесту.

    Соседи выше меряют разбор ответа на подделке ``subprocess.run``. Здесь настоящий
    подпроцесс доказывает имена и ключи команд, но не читает systemd хозяина.
    """
    calls = tmp_path / "calls"
    for tool in ("systemctl", "journalctl"):
        executable = tmp_path / tool
        executable.write_text(
            f'#!/bin/sh\nprintf \'{tool} %s\\n\' "$*" >>"$SERVICE_CALLS"\nexit 3\n',
            encoding="utf-8",
        )
        executable.chmod(0o755)
    monkeypatch.setenv("SERVICE_CALLS", str(calls))
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")

    assert unit_active("torrcast-not-a-unit") is False
    assert isinstance(unit_why("torrcast-not-a-unit"), str)
    asked = calls.read_text(encoding="utf-8")
    assert "systemctl " in asked and " is-active torrcast-not-a-unit" in asked
    assert "journalctl " in asked and " -u torrcast-not-a-unit" in asked
