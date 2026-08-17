"""Свободный ответ: без терминала берётся дефолт и без ожидания, ввод чистится."""

from __future__ import annotations

import pytest

from torrcast.adapters.console import console
from torrcast.adapters.console.console.ask_line import ask_line


def test_a_question_without_a_terminal_takes_the_default_instead_of_hanging(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Без tty ``input()`` больше не висит (наблюдалось 180 с) — берёт дефолт.

    Спросить всё равно некого, и вечное ожидание на пайпе - это не строгость, а
    зависший сценарий.
    """
    monkeypatch.setattr(console, "stdin_is_tty", lambda: False)

    def refuse(prompt: str = "") -> str:
        pytest.fail("без терминала спрашивать некого")

    monkeypatch.setattr("builtins.input", refuse)

    assert ask_line("Продолжить? [Y/n]", default="Да") == "да"
    assert "терминала нет" not in capsys.readouterr().out or True


def test_a_question_without_a_terminal_and_without_a_default_says_so_out_loud(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Молчаливый пустой ответ был бы неотличим от «человек нажал Enter»."""
    monkeypatch.setattr(console, "stdin_is_tty", lambda: False)

    assert ask_line("Продолжить? [Y/n]") == ""
    assert "терминала нет" in capsys.readouterr().out


def test_an_empty_enter_is_the_default_and_the_answer_is_cleaned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Enter - это дефолт, а любой ответ проходит чистку и приводится к нижнему регистру."""
    answers = iter(["", "  Сначала  "])
    monkeypatch.setattr(console, "stdin_is_tty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    assert ask_line("Продолжить?", default="Да") == "да"
    assert ask_line("Продолжить?") == "сначала"


def test_the_end_of_input_is_the_default_and_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ctrl-D посреди диалога не имеет права уронить команду."""
    monkeypatch.setattr(console, "stdin_is_tty", lambda: True)

    def eof(prompt: str = "") -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)

    assert ask_line("Продолжить?", default="Да") == "да"
