"""Выбор языка и подстановка диагностических строк Telegram-бота."""

from __future__ import annotations

from tgbot.catalogs.en import en as english
from tgbot.catalogs.ru import ru as russian
from torrcast.domain.invalid_config_object_error import InvalidConfigObjectError


def i18n(key: str, language: str = "en", **values: object) -> str:
    """Перевести ключ; английский служит языком и каталогом по умолчанию."""
    catalog = russian() if language == "ru" else english()
    return catalog.get(key, english()[key]).format(**values)


def _failure_detail(error: Exception, language: str) -> str:
    """Перевести структурированный отказ, а неизвестный оставить как прежде."""
    if isinstance(error, InvalidConfigObjectError):
        return i18n("invalid_config_object", language, path=error.path)
    return str(error) or type(error).__name__
