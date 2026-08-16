"""Консоль команд печатает строки и спрашивает про терминал сам модуль консоли."""

import pytest

from torrcast import console
from torrcast.adapters.console.print_console import PrintConsole


def test_a_message_is_one_line_in_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    PrintConsole().write("ТВ: 10.0.0.50")

    assert capsys.readouterr().out == "ТВ: 10.0.0.50\n"


def test_the_terminal_is_asked_about_at_every_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(console, "stdin_is_tty", lambda: False)
    assert PrintConsole().interactive() is False

    monkeypatch.setattr(console, "stdin_is_tty", lambda: True)
    assert PrintConsole().interactive() is True


def test_without_a_terminal_the_default_answers_at_once(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(console, "stdin_is_tty", lambda: False)
    talk = PrintConsole()

    assert talk.choose("Какой телевизор?", 3) == 1
    assert talk.ask("Как звать", "Ёж") == "ёж"

    printed = capsys.readouterr().out
    assert "Какой телевизор? [1]" in printed and "Как звать" in printed
