"""Консоль команд печатает строки и спрашивает про терминал на каждом вопросе."""

import pytest

from torrcast.adapters.console.print_console import PrintConsole


def test_a_message_is_one_line_in_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    PrintConsole().write("ТВ: 10.0.0.50")

    assert capsys.readouterr().out == "ТВ: 10.0.0.50\n"


def test_the_terminal_is_asked_about_at_every_call() -> None:
    """Ответ не запоминается конструктором: терминал спрашивают на каждом вопросе."""
    answers = iter([False, True, True])
    talk = PrintConsole(tty=lambda: next(answers))

    assert talk.interactive() is False
    assert talk.interactive() is True
    assert talk.interactive() is True


def test_without_a_terminal_the_default_answers_at_once(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def refuse(_prompt: str = "") -> str:
        pytest.fail("без терминала спрашивать некого")

    talk = PrintConsole(tty=lambda: False, read=refuse)

    assert talk.choose("Какой телевизор?", 3) == 1
    assert talk.ask("Как звать", "Ёж") == "ёж"

    printed = capsys.readouterr().out
    assert "Какой телевизор? [1]" in printed and "Как звать" in printed
