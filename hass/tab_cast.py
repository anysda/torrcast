"""Пульт показа вкладки, отданного «На ТВ»: команду берёт телевизор, а не вкладка.

🔴 Сторож TC-1210 (:mod:`hass.remote_refused`) узнаёт показ во вкладке по её ящику, а
«На ТВ» ящика не меняет: каст держит страница (:mod:`web.tv_session`), и отказ
``no_remote`` доставался и тогда, когда картину уже играл ТВ. Каст ЭТОГО ящика идёт -
команда уходит его приёмнику (:func:`web.tv_steer.tv_steer`), отказывать не за что.
"""

from __future__ import annotations

from torrcast.adapters.browser.read_web_box import read_web_box
from torrcast.domain.config import Config
from torrcast.usecases.playback.hls_root import hls_root
from web.tv_session import SESSION


def tab_cast(config: Config, command: str, arg: float) -> bool:
    """Каст «На ТВ» этого показа исполнил команду; каста нет или приёмник не умеет - ``False``."""
    key = str(read_web_box(hls_root(config.hls_dir)).get("key", ""))
    return bool(key) and SESSION.owns(key) and SESSION.steer(command, arg)
