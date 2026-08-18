"""Вопрос уходит в тот порт, который поставил корень, и с тем же дефолтом."""

from __future__ import annotations

import pytest

from tests.fakes.composition import use_rank_console
from tests.fakes.console import FakeConsole
from torrcast.usecases.rank.ask import ask


def test_the_question_reaches_the_installed_console(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeConsole(answers=["3"])
    use_rank_console(monkeypatch, fake)

    assert ask("Релиз?", 5, default=2) == 3
    assert fake.questions == [("Релиз?", "2")], "дефолт обязан доехать до порта нетронутым"


def test_an_empty_answer_is_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Пустой Enter - это дефолт вопроса, а не первая строка списка."""
    fake = FakeConsole()
    use_rank_console(monkeypatch, fake)

    assert ask("Релиз?", 5, default=2) == 2
