"""Выбор языка и подстановка диагностических строк Telegram-бота."""

from __future__ import annotations

from tgbot.catalogs.en import en as english
from tgbot.catalogs.ru import ru as russian


def i18n(key: str, language: str = "en", **values: object) -> str:
    """Перевести ключ; английский служит языком и каталогом по умолчанию."""
    catalog = russian() if language == "ru" else english()
    return catalog.get(key, english()[key]).format(**values)
