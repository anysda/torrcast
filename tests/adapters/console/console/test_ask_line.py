"""Свободный ответ: без терминала берётся дефолт и без ожидания, ввод чистится."""

from __future__ import annotations

from collections.abc import Callable, Iterable

import pytest

from torrcast.adapters.console.console.ask_line import ask_line


def _reader(answers: Iterable[str]) -> Callable[[str], str]:
    """Человек, отвечающий по списку: очередной ответ на очередной вопрос."""
    queue = iter(answers)

    def read(_prompt: str = "") -> str:
        return next(queue)

    return read


def test_a_question_without_a_terminal_takes_the_default_instead_of_hanging(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Без tty ``input()`` больше не висит (наблюдалось 180 с) — берёт дефолт.

    Спросить всё равно некого, и вечное ожидание на пайпе - это не строгость, а
    зависший сценарий.
    """

    def refuse(_prompt: str = "") -> str:
        pytest.fail("без терминала спрашивать некого")

    assert ask_line("Продолжить? [Y/n]", default="Да", tty=lambda: False, read=refuse) == "да"
    assert "Продолжить? [Y/n]: Да" in capsys.readouterr().out


def test_a_question_without_a_terminal_and_without_a_default_says_so_out_loud(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Молчаливый пустой ответ был бы неотличим от «человек нажал Enter»."""
    assert ask_line("Продолжить? [Y/n]", tty=lambda: False) == ""
    assert "терминала нет" in capsys.readouterr().out


def test_an_empty_enter_is_the_default_and_the_answer_is_cleaned() -> None:
    """Enter - это дефолт, а любой ответ проходит чистку и приводится к нижнему регистру."""
    read = _reader(["", "  Сначала  "])

    assert ask_line("Продолжить?", default="Да", tty=lambda: True, read=read) == "да"
    assert ask_line("Продолжить?", tty=lambda: True, read=read) == "сначала"


def test_the_end_of_input_is_the_default_and_not_a_crash() -> None:
    """Ctrl-D посреди диалога не имеет права уронить команду."""

    def eof(_prompt: str = "") -> str:
        raise EOFError

    assert ask_line("Продолжить?", default="Да", tty=lambda: True, read=eof) == "да"
