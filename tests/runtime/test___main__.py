"""Строка, которой юнит показа поднимает процесс, обязана подниматься на самом деле."""

from __future__ import annotations

import subprocess
import sys

import pytest

from torrcast.adapters.systemd.start_play_unit import start_play_unit


@pytest.mark.machine
def test_the_command_the_show_unit_starts_really_starts() -> None:
    """Берём argv у самого запуска юнита и заводим по нему настоящий процесс.

    Проверять отдельно «есть ``__main__``» было бы мимо цели: ломается не наличие файла,
    а расхождение между строкой в
    :func:`~torrcast.adapters.systemd.start_play_unit.start_play_unit` и тем, что этой
    строкой запускается. Ровно так каст и слёг: пакет
    команд развернули из модуля в каталог, а ``-m torrcast.cli`` остался - показ падал
    строкой «No module named torrcast.cli.__main__», и сухой набор молчал, потому что
    процесс поднимает systemd, а не тест.
    """
    seen: list[tuple[str, tuple[str, ...]]] = []

    def remember(tool: str, *args: str) -> subprocess.CompletedProcess[str]:
        seen.append((tool, args))
        return subprocess.CompletedProcess([tool, *args], 0, "", "")

    start_play_unit("проба", systemd=remember)

    started = [args for tool, args in seen if tool == "systemd-run"]
    assert started, "запуск юнита не позвал systemd-run"
    argv = list(started[-1])
    assert sys.executable in argv, "юнит обязан идти тем же интерпретатором"
    where = argv.index("-m")
    entry = argv[where + 1]

    # `--version` вместо `--play-key`: нужен подъём процесса, а не показ на телевизоре.
    done = subprocess.run(
        [argv[where - 1], "-m", entry, "--version"], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, f"`-m {entry}` не запускается: {done.stderr.strip()}"
    assert "torrcast" in done.stdout, done.stdout
