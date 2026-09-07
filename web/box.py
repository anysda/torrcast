"""Почтовый ящик вкладки: ``GET /api/web/box``.

Вкладка спрашивает его сама, без нашего сигнала (нет ни сокета, ни push) - страница
просто перечитывает ящик на заходе и после каждого конца показа. Второй же вкладке,
спросившей то же самое, ящик отвечает тем же заданием - запрет двух вкладок сразу тут
не заведён (ТЗ §7.4).
"""

from __future__ import annotations

import json

from torrcast.adapters.browser.read_web_box import read_web_box
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.usecases.playback.hls_root import hls_root
from web.answer import Answer
from web.request import Request
from web.tv_session import SESSION


def box(request: Request) -> Answer:
    """Отдать текущее задание вкладке; показа нет - остаётся одно слово о касте.

    Настройки читаются заново на каждый запрос: ``TORRCAST_HLS`` - подмена тестового
    прогона (:data:`torrcast.usecases.playback.hls_root.HLS_ENV`), а боевой каталог не
    меняется на ходу и кэша не стоит.
    """
    del request  # ящик один на процесс - доводов запроса ему спрашивать нечем
    out = hls_root(load_config().hls_dir)
    # ``tv`` - не про показ, а про то, где его слышно: вкладка, зашедшая на страницу уже
    # во время каста (перезагрузка, переход из карточки), иначе включила бы свою плёнку со
    # звуком поверх ТВ, потому что режим «на ТВ» до сих пор жил ТОЛЬКО в её памяти и на
    # заходе всегда начинался с «нет» (ТЗ §7.5.4).
    return Answer(200, json.dumps({**read_web_box(out), "tv": SESSION.active()}).encode())
