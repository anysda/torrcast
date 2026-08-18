"""Команда ``cast log [--since]``: выжимка недельного диагностического следа.
Зовёт её :func:`torrcast.cli.main.main`; внешних систем на пути нет.
"""

from __future__ import annotations

import contextlib
import time
from typing import Protocol

from torrcast.domain.digest import digest
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.ports.journal import journal

__all__ = ["EXIT_OK", "_cmd_log", "_since_seconds"]


class _Asked(Protocol):
    """Разобранная строка запуска в объёме, который нужен команде: одна ручка ``--since``.

    Полный :class:`torrcast.cli.args.Args` сюда не приходит нарочно: команда живёт слоем
    ниже разбора аргументов, и знать ей о нём нечего.
    """

    since: str | None


def _cmd_log(args: _Asked) -> int:
    """``cast log [--since]`` — выжимка недельного диагностического следа.

    По умолчанию - последние три сеанса; ``--since`` двигает границу (``2d``/``12h``/``30m``
    или дата ``ГГГГ-ММ-ДД``) и снимает потолок числа сеансов. Читает ту же ленту, что ведут
    поиск, отбор и показ, - никаких внешних систем, всё лежит рядом с состоянием.
    """
    since = _since_seconds(args.since)
    rows = journal().records(since)
    limit = 0 if args.since else 3
    print(digest(rows, limit=limit))
    return EXIT_OK


def _since_seconds(since: str | None) -> float:
    """``--since`` в абсолютное время: ``2d``/``12h``/``30m`` от сейчас или дата ГГГГ-ММ-ДД."""
    if not since:
        return 0.0
    units = {"d": 86400.0, "h": 3600.0, "m": 60.0}
    tail = since[-1].lower()
    if tail in units and since[:-1].isdigit():
        return time.time() - int(since[:-1]) * units[tail]
    with contextlib.suppress(ValueError, OverflowError):
        return time.mktime(time.strptime(since, "%Y-%m-%d"))  # локальная дата, как и весь след
    return 0.0
