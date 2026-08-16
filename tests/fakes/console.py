"""Записывает ввод и вывод сценариев для проверки в тестах."""

from dataclasses import dataclass, field


@dataclass
class FakeConsole:
    answers: list[str] = field(default_factory=list)
    questions: list[tuple[str, str]] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)

    def ask(self, question: str, default: str = "") -> str:
        self.questions.append((question, default))
        return self.answers.pop(0) if self.answers else default

    def write(self, message: str) -> None:
        self.messages.append(message)
