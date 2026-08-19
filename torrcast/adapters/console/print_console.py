"""Консоль команд: строки в stdout, ответы номером и вопрос «есть ли терминал».
Собирает её композиция команд (:mod:`torrcast.runtime`) для сценариев stop, status и configure.
"""

from __future__ import annotations

from collections.abc import Callable

from torrcast.adapters.console.console import stdin_is_tty as _tty
from torrcast.adapters.console.console.ask import ask
from torrcast.adapters.console.console.ask_line import ask_line


class PrintConsole:
    """Реализация консольного порта поверх прежнего диалога :mod:`torrcast.adapters.console.console`.

    Терминал и чтение строки приходят конструктором: обе связи с человеком у консоли
    одни на все три её вопроса, и стенд подставляет их объектом, а не подменой имени в
    чужом модуле. ``None`` значит «взять живые» - именно так её и собирает корень.
    """

    def __init__(
        self,
        tty: Callable[[], bool] | None = None,
        read: Callable[[str], str] | None = None,
    ) -> None:
        self._tty = tty
        self._read = read

    def ask(self, question: str, default: str = "") -> str:
        return ask_line(question, default, tty=self._tty, read=self._read)

    def choose(self, question: str, count: int, default: int = 1) -> int:
        """Вопрос с номерами: ответ - номер от 1 до ``count``, пустой Enter берёт дефолт."""
        return ask(question, count, default, tty=self._tty, read=self._read)

    def interactive(self) -> bool:
        return (_tty.stdin_is_tty if self._tty is None else self._tty)()

    def write(self, message: str) -> None:
        print(message)
