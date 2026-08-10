"""torrcast — поиск торрент-релиза и каст его на ТВ без скачивания.

Шесть модулей: :mod:`torrcast.cli` — аргументы, меню, коды выхода;
:mod:`torrcast.parse` — имена раздач, франшизы, sNeM; :mod:`torrcast.search` —
Prowlarr/Torznab; :mod:`torrcast.stream` — TorrServer, ffprobe, HLS;
:mod:`torrcast.cast` — приёмники; :mod:`torrcast.state` — конфиг и состояние.
"""

from __future__ import annotations

__all__ = ["InfraError", "NotFoundError", "SwarmError", "TorrcastError", "__version__", "why"]

__version__ = "0.1.0"


class TorrcastError(Exception):
    """Базовая ошибка: наружу печатается только ``str(exc)``, без трейсбека."""


class NotFoundError(TorrcastError):
    """Ничего не нашли по запросу. Код выхода 1."""


class InfraError(TorrcastError):
    """Легла инфраструктура: Prowlarr / TorrServer / приёмник. Код выхода 2."""


class SwarmError(InfraError):
    """Раздача не ответила: о её содержимом ничего не известно."""


#: Сетевые сбои по-русски: наружу не носим ни трейсбек, ни внутренности urllib3.
_REASONS = {
    "ConnectionError": "порт закрыт или служба не запущена",
    "ConnectTimeout": "нет ответа на подключение",
    "ReadTimeout": "не дождался ответа",
    "Timeout": "не дождался ответа",
}


def why(exc: BaseException) -> str:
    """Короткая причина сетевой ошибки для сообщения пользователю."""
    for cls in type(exc).__mro__:
        if cls.__name__ in _REASONS:
            return _REASONS[cls.__name__]
    text = str(exc).split("\n")[0].split(" for url")[0]
    return text[:100] or type(exc).__name__
