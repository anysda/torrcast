"""Разобранная строка запуска в объёме, который нужен показу: ручка ``--file N``.

Читает её выбор файла раздачи (:func:`_file_picker`).
"""

from __future__ import annotations

from typing import Protocol


class _Numbered(Protocol):
    """Разобранная строка запуска в объёме, который нужен показу: ручка ``--file N``.

    Полный :class:`torrcast.cli.args.Args` сюда не приходит: разбор аргументов стоит слоем
    выше сценариев, а показу от него нужен один отладочный номер файла.
    """

    file: int | None
