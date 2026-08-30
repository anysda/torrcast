"""Выбор языка и подстановка диагностических строк Telegram-бота."""

from __future__ import annotations

import os

from tgbot.catalogs.en import en as english
from tgbot.catalogs.ru import ru as russian

LANGUAGE_ENV = "TORRCAST_LANGUAGE"


def i18n(key: str, language: str | None = None, **values: object) -> str:
    """Перевести ключ; английский служит языком и каталогом по умолчанию."""
    selected = language or os.environ.get(LANGUAGE_ENV, "en")
    catalog = russian() if selected == "ru" else english()
    return catalog.get(key, english()[key]).format(**values)
