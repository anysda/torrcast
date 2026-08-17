"""Есть ли терминал на входе: ответ по настоящему stdin, а закрытый - это «нет»."""

from __future__ import annotations

import io
import sys

import pytest

from torrcast.adapters.console.console.stdin_is_tty import stdin_is_tty


def test_a_pipe_is_not_a_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Пайп, юнит и cron - это «терминала нет», и вопросы туда не задаются."""
    monkeypatch.setattr(sys, "stdin", io.StringIO("ответ"))

    assert stdin_is_tty() is False


def test_a_closed_stdin_is_an_answer_and_not_an_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Закрытый stdin бывает в юните показа: это «нет», а не падение команды.

    ``isatty`` на закрытом потоке бросает ``ValueError``; выпусти его наружу - и юнит
    падал бы на первом же вопросе вместо того, чтобы взять умолчание.
    """
    closed = io.StringIO()
    closed.close()
    monkeypatch.setattr(sys, "stdin", closed)

    assert stdin_is_tty() is False


def test_a_live_terminal_is_answered_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Живой терминал - это «да»: только на нём и имеет смысл кого-то спрашивать."""

    class Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr(sys, "stdin", Tty())

    assert stdin_is_tty() is True
