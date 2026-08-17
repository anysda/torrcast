"""Режим pty: ``IUTF8`` включается на время команды и возвращается как был."""

from __future__ import annotations

import os
import pty
import sys
import termios

import pytest

from torrcast.adapters.console import console
from torrcast.adapters.console.console.iutf8 import iutf8
from torrcast.adapters.console.console.terminal import terminal


def test_the_terminal_gets_iutf8_and_gives_the_mode_back() -> None:
    """IUTF8 включается на время команды и возвращается как было.

    Именно он чинит забой на кириллице: без него ssh-pty стирает один байт из двух.
    """
    parent, child = pty.openpty()
    saved = sys.stdin
    try:
        sys.stdin = open(child, encoding="utf-8")  # noqa: SIM115 - закрываем в finally
        before = termios.tcgetattr(child)
        termios.tcsetattr(child, termios.TCSANOW, [before[0] & ~iutf8(), *before[1:]])
        assert not termios.tcgetattr(child)[0] & iutf8(), "готовим pty как у ssh"

        with terminal():
            assert termios.tcgetattr(child)[0] & iutf8(), "внутри команды IUTF8 включён"

        assert not termios.tcgetattr(child)[0] & iutf8(), "режим возвращён как был"
    finally:
        sys.stdin.close()
        sys.stdin = saved
        os.close(parent)


def test_without_a_terminal_it_is_an_honest_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    """Юнит, пайп и тесты проходят насквозь: чинить трубу нечем и незачем.

    Полезь мы в ``termios`` там, где терминала нет, - показ падал бы на своём же старте.
    """
    monkeypatch.setattr(console, "stdin_is_tty", lambda: False)
    touched: list[str] = []
    monkeypatch.setattr(termios, "tcgetattr", lambda _fd: touched.append("read"))

    with terminal():
        pass

    assert touched == []
