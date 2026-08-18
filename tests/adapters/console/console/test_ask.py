"""Вопрос с номерами: цифра или Enter, чушь переспрашивается, без терминала - без петли."""

from __future__ import annotations

from collections.abc import Callable, Iterable

import pytest

from torrcast.adapters.console.console.ask import ask


def _reader(answers: Iterable[str]) -> Callable[[str], str]:
    """Человек, отвечающий по списку: очередной ответ на очередной вопрос."""
    queue = iter(answers)

    def read(_prompt: str = "") -> str:
        return next(queue)

    return read


def test_a_question_takes_a_digit_and_a_bare_enter() -> None:
    """Любой вопрос принимает и цифру, и пустой Enter."""
    read = _reader(["2", "", "  3  ", "нет", "1"])

    assert ask("Что смотрим?", 3, tty=lambda: True, read=read) == 2
    assert ask("Что смотрим?", 3, tty=lambda: True, read=read) == 1, "Enter - это дефолт"
    assert ask("Что смотрим?", 3, tty=lambda: True, read=read) == 3, "пробелы вокруг не мешают"
    assert ask("Что смотрим?", 3, tty=lambda: True, read=read) == 1, "чушь переспрашивается"


def test_a_number_outside_the_menu_is_not_an_answer() -> None:
    """Номер больше длины меню - это промах, а не выбор последнего пункта."""
    read = _reader(["9", "0", "2"])

    assert ask("Что смотрим?", 3, tty=lambda: True, read=read) == 2


def test_a_question_without_a_default_ignores_a_bare_enter() -> None:
    """Дефолта нет (``None``) - Enter не ответ: номер части называет человек.

    Любой автовыбор тут был бы подменой картины, а это самая дорогая ошибка отбора.
    """
    read = _reader(["", "2"])

    assert ask("Что смотрим?", 3, default=None, tty=lambda: True, read=read) == 2

    with pytest.raises(EOFError):
        ask("Что смотрим?", 3, default=None, tty=lambda: False, read=_reader([]))


def test_without_a_terminal_the_question_is_not_asked_twice() -> None:
    """Спросить некого - вторым кругом висеть не будем, берётся дефолт."""

    def refuse(_prompt: str = "") -> str:
        pytest.fail("без терминала спрашивать некого")

    assert ask("Что смотрим?", 3, default=2, tty=lambda: False, read=refuse) == 2
