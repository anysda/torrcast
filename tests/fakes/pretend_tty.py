"""Вход прогона, притворяющийся терминалом: живого pty под pytest нет."""

from __future__ import annotations

from typing import Any


class PretendTty:
    """Обёртка над ``sys.stdin``, у которой терминал есть, а всё прочее - настоящее.

    Врать приходится машине, а не своему коду: под pytest вход не терминал, и без этого
    вопросы консоли штатно брали бы дефолт, не спросив. Оболочкой, а не подменой ручки
    :func:`~torrcast.adapters.console.console.stdin_is_tty.stdin_is_tty`: ручка тогда
    перестала бы участвовать в прогоне вовсе - вместе со своим ``try/except`` на закрытый
    вход и вместе с каждым, кто её зовёт.
    """

    def __init__(self, stdin: Any) -> None:
        self._stdin = stdin

    def isatty(self) -> bool:
        return True

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stdin, name)
