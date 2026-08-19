"""Режим pty на время диалога: ``IUTF8`` включается и возвращается как было.

Оборачивает им весь разговор с человеком корень команды, и больше никто."""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Callable, Iterator

from torrcast.adapters.console.console import stdin_is_tty as _tty
from torrcast.adapters.console.console.iutf8 import iutf8


@contextlib.contextmanager
def terminal(tty: Callable[[], bool] | None = None) -> Iterator[None]:
    """Включить ``IUTF8`` на stdin и вернуть режим как было.

    Без него ssh-сессия ведёт себя так: русская буква занимает два байта, а
    забой стирает один — на экране остаётся половина символа, и в строку уезжает мусор.
    Флаг ставится ядром на драйвер pty, поэтому чинит и эхо, и забой разом.

    Без терминала (юнит, пайп, тесты) — честный no-op, а не попытка чинить трубу.
    Кто отвечает на «есть ли терминал», можно назвать параметром: no-op меряется тем,
    что режим никто не трогал, а не подменой имени в соседнем модуле.
    """
    if not (_tty.stdin_is_tty if tty is None else tty)():
        yield
        return
    import termios

    try:
        fd = sys.stdin.fileno()
        saved = termios.tcgetattr(fd)
    except (termios.error, ValueError, OSError):  # не pty либо stdin уже не наш
        yield
        return
    mode = list(saved)
    mode[0] = int(mode[0]) | iutf8()
    try:
        termios.tcsetattr(fd, termios.TCSANOW, mode)
        yield
    finally:
        with contextlib.suppress(termios.error, ValueError, OSError):
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)
