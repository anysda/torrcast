"""Консоль команд: строки в stdout, ответы номером и вопрос «есть ли терминал».
Собирает её композиция команд (:mod:`torrcast.runtime`) для сценариев stop, status и configure.
"""

from __future__ import annotations

from torrcast.adapters.console import console as _console


class PrintConsole:
    """Реализация консольного порта поверх прежнего диалога :mod:`torrcast.adapters.console.console`.

    Модуль зовётся по имени, а не по связанной функции: подмену вопросов на стенде
    ставят именно на него, и связывание при сборке эту подмену бы потеряло.
    """

    def ask(self, question: str, default: str = "") -> str:
        return _console.ask_line(question, default)

    def choose(self, question: str, count: int, default: int = 1) -> int:
        """Вопрос с номерами: ответ - номер от 1 до ``count``, пустой Enter берёт дефолт."""
        return _console.ask(question, count, default)

    def interactive(self) -> bool:
        return _console.stdin_is_tty()

    def write(self, message: str) -> None:
        print(message)
