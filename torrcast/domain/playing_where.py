"""Где идёт показ - словами строки «играю ... - где» (``playback.now_playing``).

Показ во вкладке писал в журнал «на ТВ»: строка знала один приёмник на всё. Вкладка
зовётся тем же словом, каким её называет выбор приёмника (``receiver.profile_browser``),
а не новой надписью.
"""

from __future__ import annotations

from torrcast.domain.catalogs.phrase import phrase


def playing_where(browser: bool) -> str:
    """«на ТВ» у показа на приёмник, имя вкладки у показа в браузере."""
    return phrase("receiver.profile_browser" if browser else "playback.where_tv")
