"""Строки Telegram-бота на языке единого держателя продукта.

Держатель один на консоль и бота (:mod:`torrcast.domain.catalogs.tongue`), и язык у
него спрашивается при КАЖДОЙ надписи, а не берётся параметром снимком: бот живёт долго,
и ``cast --ru``, посланный хоть из этого же чата, хоть с консоли соседним процессом,
обязан подействовать со следующего же ответа без рестарта юнита.
"""

from __future__ import annotations

from tgbot.catalogs.en import en as english
from tgbot.catalogs.ru import ru as russian
from torrcast.domain.catalogs.tongue import RU, tongue
from torrcast.domain.invalid_config_object_error import InvalidConfigObjectError


def i18n(key: str, **values: object) -> str:
    """Перевести ключ; английский служит языком и каталогом по умолчанию."""
    catalog = russian() if tongue() == RU else english()
    return catalog.get(key, english()[key]).format(**values)


def _failure_detail(error: Exception) -> str:
    """Перевести структурированный отказ, а неизвестный оставить как прежде."""
    if isinstance(error, InvalidConfigObjectError):
        return i18n("invalid_config_object", path=error.path)
    return str(error) or type(error).__name__
