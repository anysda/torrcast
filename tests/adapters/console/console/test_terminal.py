"""Режим pty: ``IUTF8`` включается на время команды и возвращается как был."""

from __future__ import annotations

import os
import pty
import sys
import termios
from pathlib import Path

import pytest

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


def test_without_a_terminal_it_is_an_honest_no_op(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Юнит, пайп и тесты проходят насквозь: чинить трубу нечем и незачем.

    Полезь мы в ``termios`` там, где терминала нет, - показ падал бы на своём же старте.

    ⚠️ stdin тут - НАСТОЯЩИЙ файл с рабочим ``fileno``. Под голым pytest его нет вовсе, и
    любая правка режима спотыкалась бы о ``fileno`` раньше, чем о ``termios``: тест
    оставался бы зелёным даже с выброшенной проверкой терминала, то есть не мерил бы ничего.
    """
    pipe = tmp_path / "не-терминал"
    pipe.write_text("", encoding="utf-8")
    touched: list[str] = []
    monkeypatch.setattr(termios, "tcgetattr", lambda _fd: touched.append("read"))

    with pipe.open(encoding="utf-8") as stream:
        monkeypatch.setattr(sys, "stdin", stream)
        assert sys.stdin.fileno() > 0, "стенду нужен stdin, у которого спрашивается номер"

        with terminal(tty=lambda: False):
            pass

    assert touched == []
