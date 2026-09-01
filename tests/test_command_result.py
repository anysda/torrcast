"""Словесный отказ CLI остаётся и консоли, и Telegram-обработчику."""

import io
import sys

import pytest

from tgbot.command_result import command_result


def test_command_failure_keeps_words_and_console_output(monkeypatch: pytest.MonkeyPatch) -> None:
    console = io.StringIO()
    monkeypatch.setattr("tgbot.command_result.sys.stderr", console)

    def command(_args: object) -> int:
        print("телевизор не ответил за 350 с", file=sys.stderr)
        return 2

    result = command_result(command, ["мумия"])

    assert result.code == 2
    assert result.detail == "телевизор не ответил за 350 с"
    assert console.getvalue() == "телевизор не ответил за 350 с\n"
