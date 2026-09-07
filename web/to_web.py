"""Возвращает идущий показ с ТВ в браузер: ``POST /api/to-web`` (ТЗ §7.5).

Приёмник ТВ снимается целиком (``quit_app=True``), а секунда, на которой он стоял,
уходит в ящик вкладки новым ``at`` - вкладка подхватит её на ближайшем опросе
``GET /api/web/box``. Ключ ящика не меняется: чужого сеанса тут не заводится, страница
остаётся той же вкладкой, что играла ДО «На ТВ».
"""

from __future__ import annotations

from torrcast.adapters.browser.read_web_box import read_web_box
from torrcast.adapters.browser.write_web_box import write_web_box
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.usecases.playback.hls_root import hls_root
from web.answer import Answer
from web.refusal import refusal
from web.request import Request
from web.tv_session import SESSION


def to_web(request: Request) -> Answer:
    """Снять каст и вернуть секунду ТВ в ящик вкладки как новое ``at``."""
    del request  # тело запросу не нужно - вся секунда берётся у самого приёмника ТВ
    if not SESSION.active():
        return refusal(409, "not_casting")
    at = SESSION.stop()
    out = hls_root(load_config().hls_dir)
    box = read_web_box(out)
    if box:  # показ мог кончиться сам, пока играл на ТВ - обновлять тогда нечего
        write_web_box(
            out, url=str(box["url"]), title=str(box.get("title", "")), at=at, key=str(box["key"])
        )
    return Answer(202, b"")
