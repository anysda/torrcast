"""Поля настроек про хозяйство показа: кому играем, где ищем и откуда раздаём.

Читает их :class:`torrcast.domain.config.Config`, и только он.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(slots=True)
class _ConfigSources:
    """Приёмник, поиск и раздача: с кем показ разговаривает по сети."""

    tv: str | None = None
    receiver: Literal["chromecast", "mock"] = "chromecast"
    #: Профиль приёмника РУКАМИ (:mod:`torrcast.domain.profile`): ``q70d``, ``androidtv``.
    #:
    #: **Пусто - нормальный режим**: профиль выбирается сам, по паспорту устройства, и
    #: спрашивать об этом человека не надо. Задавать стоит ровно в двух случаях: приёмник
    #: незнакомый, а его пороги уже известны, - или наоборот, хочется прибить осторожный
    #: набор на знакомом. Незнакомое имя тут не ошибка: будет осторожный профиль.
    receiver_profile: str = ""
    torrserver_url: str = "http://127.0.0.1:8090"
    prowlarr_url: str = "http://127.0.0.1:9696"
    prowlarr_apikey: str = ""
