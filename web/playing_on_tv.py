"""Идёт ли ИМЕННО эта картина на телевизоре - признак кнопок карточки (:mod:`web.card`).

Карточка ставит «Подключиться»/«Завершить» вместо «PLAY ON TV» той картине, к показу
которой зрителю есть куда подключиться. Показ в самой вкладке таким не является:
приёмника, у которого можно забрать картину, там нет, и подключаться не к чему.
"""

from __future__ import annotations

from torrcast.adapters.browser.read_web_box import read_web_box
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.ports.show_unit.slot import unit
from torrcast.ports.state_store.slot import store
from torrcast.usecases.playback.hls_root import hls_root
from web.tv_live import tv_live


def playing_on_tv(key: str) -> bool:
    """Показ этой картины идёт и он на ТВ; иначе карточка живёт обычным набором кнопок.

    Хэш, который не снял оборванный снос, без живого юнита показом не считается - это
    прежний порядок признака. Новое тут одно: вопрос о МЕСТЕ показа (:mod:`web.tv_live`).
    Настройки читаются заново, как и у ящика: ``TORRCAST_HLS`` подменяет каталог в прогоне.
    """
    showing = store().load().showing()
    if showing is None or showing[0] != key or not unit().active():
        return False
    return tv_live(read_web_box(hls_root(load_config().hls_dir)))
