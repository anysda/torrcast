"""Проверяет консоль на подставленных потоках."""

from io import StringIO

from torrcast.adapters.console.terminal_console import TerminalConsole


def test_non_terminal_returns_clean_default() -> None:
    output = StringIO()
    console = TerminalConsole(StringIO(), output)

    assert console.ask("Имя", "  Ёж\x00 ") == "ёж"
    assert output.getvalue() == "Имя:   Ёж\x00 \n"
