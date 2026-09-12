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
from torrcast.ports.state_store.slot import store
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
    seen = read_web_box(out)
    # ``tv`` - не про показ, а про то, где его слышно: вкладка, зашедшая на страницу уже
    # во время каста (перезагрузка, переход из карточки), иначе включила бы свою плёнку со
    # звуком поверх ТВ, потому что режим «на ТВ» до сих пор жил ТОЛЬКО в её памяти и на
    # заходе всегда начинался с «нет» (ТЗ §7.5.4). Слово о касте приходит теперь ДВУМЯ
    # путями: `SESSION` знает про перенос «На ТВ» из вкладки (:mod:`web.tv_session`), а
    # сам ящик - про показ, поднятый СРАЗУ на ТВ (:mod:`torrcast.usecases.playback._play`
    # пишет ``tv: true`` любому приёмнику, кроме вкладки) - вторая вкладка обязана
    # заглушить себя и в этом случае тоже (TC-1224).
    #
    # 🔴 Второй путь сам не лечится: `SESSION.settle` снимает осиротевший каст ЭТОГО
    # держателя, но показ, поднятый сразу на ТВ, снимается «Завершить» одним - «cast
    # stop» или конец картины ящик не трогают вовсе, и раз написанное ``tv: true``
    # переживало показ навсегда (стенд `.104` 13-09-2026: «Матрица» снята «cast stop»,
    # `/api/state` честно ушёл в ``idle``, а `/api/web/box` всё ещё звал её играющей).
    # Подключившаяся вкладка тогда глохла НАВСЕГДА - слово со звуком отдаёт только
    # «Вернуть на компьютер», а ему неоткуда взяться без нового показа. Раз ничего не
    # играет вовсе (:meth:`torrcast.domain.watch_state.WatchState.showing`, тот же
    # признак, каким живут кнопки карточки, TC-1225), сырому слову ящика веры нет.
    live = bool(seen.get("tv", False)) and store().load().showing() is not None
    return Answer(
        200,
        json.dumps({**seen, "tv": live or SESSION.settle(str(seen.get("key", "")))}).encode(),
    )
