"""Лента меток секундомера из файла как таблица."""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.filesystem.stopwatch.read import read
from torrcast.domain.report import report


def stopwatch_report(path: str | Path, zero: str = "") -> str:
    """Лента меток из файла как таблица: прочитать и свести одной строкой.

    ``zero`` - метка, от которой считается ноль; пусто - от первой метки.
    """
    return report(read(path), zero)
