"""Собирает адрес ленты последних раздач Prowlarr: без строки поиска, узкой категорией."""

from __future__ import annotations

from typing import Final
from urllib.parse import quote

from torrcast.adapters.prowlarr.search_url import SEARCH_PATH

#: Кино и сериалы - и только они: софт, музыка и книги ленте не нужны (ТЗ §9).
FEED_CATEGORIES: Final = (2000, 5000)


def feed_url(base_url: str, apikey: str, limit: int) -> str:
    """Адрес ленты последних раздач: тот же агрегат, но без ``query``.

    Замерено на живом стенде: агрегат ``/api/v1/search`` без строки поиска отдаёт
    последние раздачи всех индексеров одним запросом (107 строк от 5 индексеров) -
    отдельного кругового опроса (:meth:`torrcast.adapters.prowlarr.prowlarr.Prowlarr._apart`)
    лента не заводит, он ей не нужен.
    """
    cats = "".join(f"&categories={c}" for c in FEED_CATEGORIES)
    return f"{base_url}{SEARCH_PATH}?apikey={quote(apikey)}&type=search&limit={limit}{cats}"


__all__ = ["FEED_CATEGORIES", "feed_url"]
