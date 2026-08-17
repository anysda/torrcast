"""Проверяет область юнита и то, что вызов systemd не роняет команду на чужой беде."""

from __future__ import annotations

import os
import subprocess
from typing import Any

import pytest

from torrcast.adapters.systemd import _systemd_call


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
