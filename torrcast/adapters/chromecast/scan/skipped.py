"""Одна строка о подсетях, которые обходить не стали: молчать о них нельзя.

Говорит её поиск приёмников перед меню, и ровно один раз на все такие подсети."""

from __future__ import annotations

from torrcast.domain.catalogs.phrase import phrase


def skipped(huge: list[str]) -> str:
    """Одна строка о подсетях, которые мы обходить не стали. Пусто - и говорить не о чем."""
    if not huge:
        return ""
    return phrase("chromecast_scan.subnets_skipped", names=", ".join(huge))
