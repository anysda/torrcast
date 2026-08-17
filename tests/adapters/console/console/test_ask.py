"""Вопрос с номерами: цифра или Enter, чушь переспрашивается, без терминала - без петли."""

from __future__ import annotations

import pytest

from torrcast.adapters.console import console
from torrcast.adapters.console.console.ask import ask


def test_a_question_takes_a_digit_and_a_bare_enter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Любой вопрос принимает и цифру, и пустой Enter."""
    answers = iter(["2", "", "  3  ", "нет", "1"])
    monkeypatch.setattr(console, "stdin_is_tty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    assert ask("Что смотрим?", 3) == 2
    assert ask("Что смотрим?", 3) == 1, "Enter - это дефолт"
    assert ask("Что смотрим?", 3) == 3, "пробелы вокруг цифры не мешают"
    assert ask("Что смотрим?", 3) == 1, "чушь переспрашивается, а не падает"


def test_a_number_outside_the_menu_is_not_an_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Номер больше длины меню - это промах, а не выбор последнего пункта."""
    answers = iter(["9", "0", "2"])
    monkeypatch.setattr(console, "stdin_is_tty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    assert ask("Что смотрим?", 3) == 2


def test_a_question_without_a_default_ignores_a_bare_enter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Дефолта нет (``None``) - Enter не ответ: номер части называет человек.

    Любой автовыбор тут был бы подменой картины, а это самая дорогая ошибка отбора.
    """
    answers = iter(["", "2"])
    monkeypatch.setattr(console, "stdin_is_tty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    assert ask("Что смотрим?", 3, default=None) == 2

    monkeypatch.setattr(console, "stdin_is_tty", lambda: False)
    with pytest.raises(EOFError):
        ask("Что смотрим?", 3, default=None)


def test_without_a_terminal_the_question_is_not_asked_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Спросить некого - вторым кругом висеть не будем, берётся дефолт."""
    monkeypatch.setattr(console, "stdin_is_tty", lambda: False)

    assert ask("Что смотрим?", 3, default=2) == 2
