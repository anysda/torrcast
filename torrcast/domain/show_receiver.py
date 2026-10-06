"""Приёмник ОДНОГО запуска показа: вкладка, если просила она, иначе телевизор машины.

``here`` - слово страницы «играй у меня» (:mod:`hass.play_extras`). Его молчание - это кнопка
«PLAY ON TV» карточки, Home Assistant и бот, и все они зовут показ на телевизор. Машина с
приёмником-вкладкой (``receiver: browser``) и названным ``tv`` - законная пара: смотрю обычно
во вкладке, но телевизор рядом есть. Читая там ``config.receiver`` как есть, запуск без
``here`` снова доставался вкладке, которая играть его не просила: экран висел
``0:00:00 · BUFFERING``, а телевизор задания не получал вовсе (TC-1370).
"""

from __future__ import annotations

from dataclasses import replace

from torrcast.domain.config import Config

__all__ = ["show_receiver"]


def show_receiver(config: Config, here: bool) -> Config:
    """Настройки запуска с его приёмником; настройка машины при этом не пишется.

    ``here`` - вкладка. Без него - ``config.receiver``, кроме вкладки при названном ``tv``:
    тогда телевизор. ``tv``, равный слову ``browser``, телевизором не считается
    (:func:`torrcast.domain.for_tab.for_tab`).
    """
    if here:
        return replace(config, receiver="browser")
    tv = str(config.tv or "")
    if config.receiver == "browser" and tv not in ("", "browser"):
        return replace(config, receiver="chromecast")
    return config
