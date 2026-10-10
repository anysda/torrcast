"""Фоновой задаче терминал не отвечает: проверка на настоящем pty, а не на подделке входа."""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

_PROBE = textwrap.dedent(
    """
    import os, sys
    from torrcast.adapters.console.console.stdin_is_tty import stdin_is_tty

    os.setsid()
    master, slave = os.openpty()
    name = os.ttyname(slave)
    os.close(slave)
    tty = os.open(name, os.O_RDWR)  # лидер сессии без терминала берёт его управляющим
    os.dup2(tty, 0)
    sys.stdin = open(0, closefd=False)

    def child(background):
        pid = os.fork()
        if pid == 0:
            if background:
                os.setpgid(0, 0)  # так делает timeout без --foreground
            os._exit(0 if stdin_is_tty() else 1)
        return os.waitpid(pid, 0)[1] >> 8

    print(child(False), child(True))
    """
)


@pytest.mark.machine
@pytest.mark.skipif(sys.platform == "win32", reason="группы процессов и pty - только POSIX")
def test_a_background_process_group_has_no_terminal() -> None:
    """``timeout 300 cast ...`` под pty висел дольше срока: SIGTTOU на смене режима входа.

    ``timeout`` без ``--foreground`` уводит команду в свою группу, и терминал для неё
    фоновый. Спроси команда режим или вопрос у такого терминала - ядро её остановит,
    и стоять она будет, пока её не продолжат руками. Передний план отвечает «да» (0),
    фоновая группа на том же терминале - «нет» (1).
    """
    done = subprocess.run(
        [sys.executable, "-c", _PROBE], capture_output=True, text=True, timeout=30, check=True
    )

    assert done.stdout.split() == ["0", "1"]
