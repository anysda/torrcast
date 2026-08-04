"""torrcast — поиск торрент-релиза и каст его на ТВ без скачивания.

Пакет из шести модулей (§6 ТЗ):

* :mod:`torrcast.cli`    — разбор аргументов, меню, коды выхода;
* :mod:`torrcast.parse`  — парсер имён раздач, кластеризация франшиз, sNeM;
* :mod:`torrcast.search` — Prowlarr/Torznab;
* :mod:`torrcast.stream` — TorrServer, ffprobe, упаковка в HLS;
* :mod:`torrcast.cast`   — приёмники: Chromecast и mock;
* :mod:`torrcast.state`  — конфиг и состояние просмотра.
"""

from __future__ import annotations

__all__ = ["InfraError", "NotFoundError", "TorrcastError", "__version__"]

__version__ = "0.1.0"


class TorrcastError(Exception):
    """Базовая ошибка torrcast.

    Наружу печатается только ``str(exc)`` — одна короткая строка по-русски,
    без трейсбека (§6 ТЗ).
    """


class NotFoundError(TorrcastError):
    """Ничего не нашли по запросу. Код выхода 1."""


class InfraError(TorrcastError):
    """Легла инфраструктура: Prowlarr / TorrServer / приёмник. Код выхода 2."""
