"""Что вкладка сказала о себе: ключ по куке умений и ``User-Agent``.

Показ получает ключ ЭТОГО запроса довод за доводом (``--tab``), и чужая вкладка его не
подменит. Последний услышанный ключ помнится для поиска и прогрева
(:func:`web.tab_detect.tab_detect`), которым довода не протянуть.
"""

from __future__ import annotations

from collections.abc import Mapping
from http.cookies import CookieError, SimpleCookie

from torrcast.domain.tab_key import TAB_COOKIE, tab_key

__all__ = ["hear"]

_HEARD: dict[str, str] = {"tab": ""}


def _said(cookie: str) -> str | None:
    """Значение куки умений; нет её или кука кривая - вкладка ничего не сказала."""
    jar: SimpleCookie = SimpleCookie()
    try:
        jar.load(cookie)
    except CookieError:
        return None
    morsel = jar.get(TAB_COOKIE)
    return None if morsel is None else morsel.value


def hear(headers: Mapping[str, str]) -> str:
    """Ключ вкладки этого запроса; непустой запоминается для поиска и прогрева."""
    named = {name.lower(): value for name, value in headers.items()}
    tab = tab_key(named.get("user-agent", ""), _said(named.get("cookie", "")))
    if tab:
        _HEARD["tab"] = tab
    return tab
