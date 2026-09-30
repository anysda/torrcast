"""Щедрые пороги вкладки - только тому браузеру, на котором они замерены.

Ключ вкладки (:func:`torrcast.domain.tab_key.tab_key`) называет движок и систему.
Замерены :data:`MEASURED`: тот же ``scripts/tabprobe.py`` и тот же hls.js гоняли куски
58 и 80 МБ по 15 с на Chromium и Firefox настольного Linux, чисто на обоих, а 115 МБ не
держит ни один. Всем прочим, включая WebKit, iOS, Android, macOS и Windows, достаются
прежние осторожные пороги, ровно как в ``dev``: незамеренный браузер не хуже, чем был.
"""

from __future__ import annotations

from typing import Final

from torrcast.domain.browser_profile import BROWSER
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.choice import Choice
from torrcast.domain.config import Config

__all__ = ["MEASURED", "for_tab"]

#: Ключи вкладок, на которых сняты пороги :data:`torrcast.domain.browser_profile.BROWSER`.
#: снято: tabprobe · mpegts · TC-1259
MEASURED: Final = frozenset({"chromium-linux", "gecko-linux"})


def for_tab(chosen: Choice, config: Config, tab: str) -> Choice:
    """Профиль показа с поправкой на вкладку, сказавшую о себе ``tab``.

    Поправка трогает только машину, где играет одна вкладка и передать показ некому
    (приёмник ``browser``, ``tv`` пуст или то же слово), а профиль руками не назван. Там
    замеренная вкладка получает :data:`BROWSER`, а остальные - то, что выбрал бы ``dev``.
    Машина с ТВ играет во вкладке поток телевизора, и её выбор не меняется.
    """
    alone = config.receiver == "browser" and str(config.tv or "") in ("", "browser")
    if not tab or not alone or config.receiver_profile:
        return chosen
    if tab in MEASURED:
        return Choice(BROWSER, phrase("profile_detector.browser_tab", tab=tab))
    return Choice(chosen.profile, phrase("profile_detector.tab_unmeasured", tab=tab))
