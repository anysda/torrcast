"""Проверяет область задания и то, что вызов launchd не роняет команду на чужой беде."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from torrcast.adapters.launchd import _launchd_call
from torrcast.adapters.launchd.job_active import job_active


def test_the_domain_is_the_user_one_unless_we_are_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """Постоянных заданий нет ни там, ни там, но область у транзитного обязана совпадать.

    Промахнись область - и ``bootout`` гасит пустоту, а ``status`` докладывает, что
    показа нет, пока показ идёт.
    """
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    assert _launchd_call._domain() == "system"
    monkeypatch.setattr(os, "geteuid", lambda: 502)
    assert _launchd_call._domain() == "gui/502"


def test_the_call_never_raises_on_a_bad_return_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ненулевой код разбирает зовущий, а не исключение.

    Отсутствие задания - обычный ответ ``launchctl``, и падать на нём команде нельзя:
    ``cast stop`` без показа обязан молча кончиться.
    """
    seen: list[tuple[list[str], dict[str, Any]]] = []

    def remember(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.append((command, kwargs))
        return subprocess.CompletedProcess(command, 3, "", "No such process")

    monkeypatch.setattr(subprocess, "run", remember)
    done = _launchd_call._launchd("launchctl", "bootout", "gui/502/torrcast-play")

    assert done.returncode == 3, "ненулевой код обязан доехать до зовущего"
    command, kwargs = seen[-1]
    assert command == ["launchctl", "bootout", "gui/502/torrcast-play"]
    assert kwargs["check"] is False, "чужой код возврата не наша авария"
    assert kwargs["text"] is True and kwargs["capture_output"] is True
    assert kwargs["timeout"] > 0, "без потолка повисший launchctl вешает команду навсегда"


def test_only_the_top_level_state_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    """У вложенных секций ``print`` свои ``state``: чужая ``active`` - не живой показ."""
    answer = "\tstate = not running\n\tsockets = {\n\t\tstate = active\n\t}\n"
    assert _launchd_call._running(answer) is False
    assert _launchd_call._running("\tstate = running\n") is True


def test_the_plumbing_answers_about_a_job_that_does_not_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Разговор с командой настоящий, а launchctl принадлежит тесту.

    Соседи выше меряют подменённый ``subprocess.run``. Здесь настоящий подпроцесс
    доказывает имя и доводы команды, не читая launchd хозяина; поэтому та же проба
    осмысленно работает и на Linux.
    """
    calls = tmp_path / "calls"
    launchctl = tmp_path / "launchctl"
    launchctl.write_text(
        '#!/bin/sh\nprintf \'%s\\n\' "$*" >>"$LAUNCHD_CALLS"\nexit 113\n',
        encoding="utf-8",
    )
    launchctl.chmod(0o755)
    monkeypatch.setenv("LAUNCHD_CALLS", str(calls))
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")

    assert job_active("torrcast.not-a-job") is False
    assert calls.read_text(encoding="utf-8").endswith("/torrcast.not-a-job\n")
