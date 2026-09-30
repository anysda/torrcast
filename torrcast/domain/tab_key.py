"""Ключ вкладки: что она сказала о себе кукой умений и что видно по ``User-Agent``.

Страница кладёт куку ``tc_tab`` со списком умений через точку (``mse``, ``mms``, ``hls``,
``avc51``, ``hevc``), а движок и система видны по ``User-Agent``. Из этого получается ключ
``движок-система``, а у вкладки без MSE или без h264 High 5.1 к нему дописано ``-bare``.
Слова ключа - из закрытого списка, и в командную строку показа он едет как есть.
"""

from __future__ import annotations

from typing import Final

__all__ = ["TAB_COOKIE", "tab_key"]

#: Кука, которой страница говорит свои умения (``web/static/api.js``).
TAB_COOKIE: Final = "tc_tab"


def _engine(agent: str) -> str:
    """Движок по ``User-Agent``; на iOS любой браузер - WebKit (CriOS и FxiOS тоже)."""
    if any(word in agent for word in ("iPhone", "iPad", "iPod")):
        return "webkit"
    if "Firefox/" in agent:
        return "gecko"
    if "Chrome/" in agent or "Chromium/" in agent:
        return "chromium"
    return "webkit" if "AppleWebKit" in agent else "other"


def _system(agent: str) -> str:
    """Система по ``User-Agent``. Android - тоже Linux, поэтому он спрашивается раньше."""
    for word, system in (
        ("iPhone", "ios"), ("iPad", "ios"), ("iPod", "ios"), ("Android", "android"),
        ("CrOS", "cros"), ("Windows", "windows"), ("Macintosh", "mac"), ("Linux", "linux"),
    ):  # fmt: skip
        if word in agent:
            return system
    return "other"


def tab_key(agent: str, said: str | None) -> str:
    """Ключ вкладки по ``User-Agent`` и куке умений; куки нет - вкладка молчала, ключ пуст."""
    if said is None:
        return ""
    can = set(said.split("."))
    bare = not ({"mse", "mms"} & can) or "avc51" not in can
    return f"{_engine(agent)}-{_system(agent)}" + ("-bare" if bare else "")
