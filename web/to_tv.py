"""Переносит идущий показ на ТВ: ``POST /api/to-tv`` (ТЗ §7.5).

Поток, упаковка и перекод не трогаются: приёмнику ТВ достаётся тот же ``url``, что уже
лежит в ящике вкладки (:mod:`web.box`), и та же секунда, на которой стоит показ - нового
показа тут не поднимается.
"""

from __future__ import annotations

from torrcast.adapters.browser.read_web_box import read_web_box
from torrcast.adapters.browser.read_web_position import read_web_position
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.usecases.playback.hls_root import hls_root
from web.answer import Answer
from web.refusal import refusal
from web.request import Request
from web.tv_session import SESSION


def to_tv(request: Request) -> Answer:
    """Позвать приёмник ``config.tv`` на уже идущий показ вкладки."""
    del request  # тело запросу не нужно - всё берётся из ящика вкладки и настроек
    config = load_config()
    address = config.tv or ""
    if not address:
        return refusal(409, "no_tv")
    out = hls_root(config.hls_dir)
    box = read_web_box(out)
    url = str(box.get("url", ""))
    if not url:
        return refusal(409, "nothing_playing")
    # Позиция от вкладки свежее позиции ящика, только пока она про ЭТОТ сеанс: чужой или
    # прошлый ключ был бы враньём о секунде показа (тем же основанием, что и `web.position`).
    record = read_web_position(out)
    at = float(box.get("at", 0.0))
    if record is not None and record.get("key") == box.get("key"):
        at = float(record.get("pos", at))
    SESSION.start(address, str(box.get("title", "")), url, at)
    return Answer(204, b"")
