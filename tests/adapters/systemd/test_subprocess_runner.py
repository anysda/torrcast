"""Проверяет результат запуска на безопасной локальной команде."""

import subprocess
from types import SimpleNamespace

from torrcast.adapters.systemd.subprocess_runner import SubprocessRunner


def test_captures_process_result(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="готово\n", stderr=""),
    )
    done = SubprocessRunner().run(["program"])

    assert done.returncode == 0
    assert done.stdout == "готово\n"
