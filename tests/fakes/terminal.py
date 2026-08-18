"""Терминал стенду: есть человек у консоли или нет.

Под pytest терминала нет вовсе, а вопросы проверять надо, поэтому по умолчанию стенд
притворяется терминалом (фикстура ``_pretend_tty`` в ``tests/conftest.py``). Тестам, чей
предмет - как раз неинтерактивный запуск (ssh без pty, скрипт из cron), нужно обратное, и
берут они его отсюда: имя, которым консоль отвечает на этот вопрос, названо в одном месте,
а не в каждом тесте по отдельности.
"""

from __future__ import annotations

import pytest

from torrcast.adapters.console import console


def use_tty(patch: pytest.MonkeyPatch, *, tty: bool) -> None:
    """Сказать стенду, есть ли терминал у запуска."""
    patch.setattr(console, "stdin_is_tty", lambda: tty)
