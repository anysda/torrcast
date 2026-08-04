"""torrcast — поиск торрент-релиза и каст его на ТВ без скачивания.

Шесть модулей (§6 ТЗ): :mod:`torrcast.cli` — аргументы, меню, коды выхода;
:mod:`torrcast.parse` — имена раздач, франшизы, sNeM; :mod:`torrcast.search` —
Prowlarr/Torznab; :mod:`torrcast.stream` — TorrServer, ffprobe, HLS;
:mod:`torrcast.cast` — приёмники; :mod:`torrcast.state` — конфиг и состояние.
"""

from __future__ import annotations

__all__ = ["InfraError", "NotFoundError", "TorrcastError", "__version__"]

__version__ = "0.1.0"


class TorrcastError(Exception):
    """Базовая ошибка: наружу печатается только ``str(exc)``, без трейсбека (§6 ТЗ)."""


class NotFoundError(TorrcastError):
    """Ничего не нашли по запросу. Код выхода 1."""


class InfraError(TorrcastError):
    """Легла инфраструктура: Prowlarr / TorrServer / приёмник. Код выхода 2."""
