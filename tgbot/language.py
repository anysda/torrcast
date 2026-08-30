"""Язык бота и мастера настройки: та же настройка продукта, что и у ``cast``."""

from __future__ import annotations

from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.domain.torrcast_error import TorrcastError


def language() -> str:
    """Спросить язык у настройки продукта.

    🔴 Спрашивается на КАЖДЫЙ ответ, а не один раз при старте: бот живёт долго, и
    ``cast --ru``, посланный из того же чата, обязан подействовать со следующей же
    команды, а не после рестарта юнита.

    Битая настройка тут не роняет опрос обновлений: язык - это оформление ответа, а сам
    отказ читать настройку человек всё равно увидит словом, потому что на битом файле
    падает сама команда, и бот назовёт её отказ (``failed``).
    """
    try:
        return load_config().language
    except TorrcastError:
        return "en"
