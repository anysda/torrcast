"""Записывает ввод и вывод сценариев для проверки в тестах."""

from dataclasses import dataclass, field


@dataclass
class FakeConsole:
    answers: list[str] = field(default_factory=list)
    questions: list[tuple[str, str]] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    tty: bool = True

    def ask(self, question: str, default: str = "") -> str:
        self.questions.append((question, default))
        return self.answers.pop(0) if self.answers else default

    def choose(self, question: str, count: int) -> int:
        """Ответ номером: без заготовленного ответа берётся первый пункт, как пустой Enter."""
        answer = self.ask(question, "1")
        return int(answer) if answer.isdigit() and 1 <= int(answer) <= count else 1

    def interactive(self) -> bool:
        return self.tty

    def write(self, message: str) -> None:
        self.messages.append(message)
