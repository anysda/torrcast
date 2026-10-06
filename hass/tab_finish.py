"""Команда вкладке закончить серию тем же путём, что её естественный конец."""

from __future__ import annotations

from hass.remote_refused import _tab_receiver
from torrcast.adapters.browser.read_web_box import read_web_box
from torrcast.adapters.browser.write_web_finish import write_web_finish
from torrcast.domain.config import Config
from torrcast.usecases.playback.hls_root import hls_root
from web.tv_session import SESSION


def tab_finish(config: Config, at: float) -> bool:
    """Послать вкладке её собственную команду конца; не вкладке - ``False``.

    Обычный пульт вкладка по-прежнему не получает. Здесь намеренно отдельная команда:
    стрелка не управляет ею, а только просит пройти уже существующий путь конца потока.
    """
    out = hls_root(config.hls_dir)
    box = read_web_box(out)
    key = str(box.get("key", ""))
    if not _tab_receiver(config) or not key or SESSION.owns(key):
        return False
    write_web_finish(out, key, at)
    return True
