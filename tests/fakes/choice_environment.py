"""Окружение выбора для тестов: ответы на вопросы даёт тест, остальное - как в бою.

Вопрос и терминал - единственное, что в меню картин подделывается: правила отбора,
справка и печать остаются настоящими, иначе проверялся бы не выбор, а сама подделка.
"""

from dataclasses import dataclass, field
from typing import Any

from torrcast.adapters.choice_environment import environment


@dataclass
class FakeChoiceEnvironment:
    #: Номера, которые называет человек, по одному на вопрос. Кончились - это Enter.
    answers: list[int] = field(default_factory=list)
    tty: bool = True
    questions: list[tuple[str, int, int | None]] = field(default_factory=list)

    def __getattr__(self, name: str) -> Any:
        """Всё, чего тест не подделывает, спрашивается у настоящего окружения."""
        return getattr(environment, name)

    def stdin_is_tty(self) -> bool:
        return self.tty

    def ask(self, question: str, count: int, default: int | None = 1) -> int:
        """Ответ номером; без заготовленного номера это пустой Enter, то есть дефолт."""
        self.questions.append((question, count, default))
        if self.answers:
            return self.answers.pop(0)
        if default is None:
            raise AssertionError(f"вопрос «{question}» без дефолта, а ответа тест не дал")
        return default
