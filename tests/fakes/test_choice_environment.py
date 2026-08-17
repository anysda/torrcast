"""Зеркало окружения выбора: ответы, терминал и всё остальное из настоящего окружения."""

import pytest

from tests.fakes.choice_environment import FakeChoiceEnvironment


def test_prepared_numbers_are_given_out_in_order() -> None:
    environment = FakeChoiceEnvironment(answers=[2, 1])

    assert environment.ask("Что смотрим?", 3) == 2
    assert environment.ask("Что смотрим?", 3) == 1
    assert environment.questions == [("Что смотрим?", 3, 1), ("Что смотрим?", 3, 1)]


def test_an_empty_answer_is_the_default_that_enter_would_take() -> None:
    assert FakeChoiceEnvironment().ask("Что смотрим?", 3, default=2) == 2


def test_a_question_without_a_default_needs_a_real_answer() -> None:
    with pytest.raises(AssertionError):
        FakeChoiceEnvironment().ask("Что смотрим?", 3, default=None)


def test_the_terminal_is_told_as_the_test_asked() -> None:
    assert FakeChoiceEnvironment().stdin_is_tty()
    assert not FakeChoiceEnvironment(tty=False).stdin_is_tty()


def test_the_rest_is_the_real_environment() -> None:
    """Пороги и правила подделке не принадлежат: их спрашивают у настоящего окружения."""
    assert FakeChoiceEnvironment().alive_seeders == 5
