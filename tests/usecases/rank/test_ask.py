"""Вопрос уходит в тот порт, который поставил корень, и с тем же дефолтом."""

from __future__ import annotations

from importlib import import_module

import pytest

from tests.fakes.console import FakeConsole
from torrcast.usecases.rank.ask import ask

#: ⚠️ Модулем, а не атрибутом пакета: у пакета имя `configure` занято одноимённой
#: единицей, и подмена на функции ставится в никуда - молча.
_slot = import_module("torrcast.usecases.rank.configure")


def test_the_question_reaches_the_installed_console(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeConsole(answers=["3"])
    monkeypatch.setattr(_slot, "_console", fake, raising=False)

    assert ask("Релиз?", 5, default=2) == 3
    assert fake.questions == [("Релиз?", "2")], "дефолт обязан доехать до порта нетронутым"


def test_an_empty_answer_is_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Пустой Enter - это дефолт вопроса, а не первая строка списка."""
    fake = FakeConsole()
    monkeypatch.setattr(_slot, "_console", fake, raising=False)

    assert ask("Релиз?", 5, default=2) == 2
