"""Место показа от вкладки: ``POST /api/web/position``.

Единственная дверь, которой позиция браузера входит в продукт: записанное отсюда
читает :meth:`torrcast.adapters.browser.browser_receiver.BrowserReceiver.position`, а
дальше закладку двигает тот же код, что и для приставки (ТЗ §7.2) - второго писателя
:class:`torrcast.domain.watch_state.WatchState` тут нет и не заводится.
"""

from __future__ import annotations

from typing import TypeGuard

from torrcast.adapters.browser.read_web_box import read_web_box
from torrcast.adapters.browser.write_web_position import write_web_position
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.system_clock import CLOCK
from torrcast.domain.json_value import JsonValue
from torrcast.usecases.playback.hls_root import hls_root
from web.answer import Answer
from web.refusal import refusal
from web.request import Request
from web.tv_session import SESSION

#: Слова состояния, которые вкладка вправе назвать. Не про удобство: чужое слово тут
#: молча легло бы в держатель показа (:func:`torrcast.usecases.revive_playback._hold._hold`)
#: и было бы прочитано как ЕГО состояние - строка без проверки на входе врёт тише всего.
#: ``left`` - не состояние плёнки, а слово страницы о самой себе: «ухожу» (закрытие
#: вкладки, уход с ``/play``), - и решает по нему один
#: :meth:`torrcast.adapters.browser.browser_receiver.BrowserReceiver.position` (TC-1124).
_PHASES = frozenset({"playing", "paused", "buffering", "ended", "left"})


def _is_number(value: JsonValue) -> TypeGuard[int | float]:
    """``bool`` - тоже ``int`` для питона, а не для позиции в ролике."""
    return isinstance(value, int | float) and not isinstance(value, bool)


def position(request: Request) -> Answer:
    """Принять позицию текущего сеанса; чужой или устаревший ключ - отказ ``409``."""
    body = request.body
    key = str(body.get("key", ""))
    out = hls_root(load_config().hls_dir)
    box = read_web_box(out)
    if not key or key != box.get("key"):
        return refusal(409, "stale_key")
    # Пока показ на ТВ, закладку двигает приёмник, а не вкладка (ТЗ §7.5.3): страница
    # остаётся слушать и докладывать (её плёнка идёт беззвучно и подстраивается, §4.5),
    # но её секунда - не та, по которой продукт помнит место. Отказом это не отвечается:
    # доклад принят, писать по нему нечего. Ключ сверяется ДО - 409 остаётся единственным
    # сигналом вкладке, что ящик подменили (``web/static/player-box.js``). И молчит она
    # только про ТОТ показ, который на ТВ и есть: каст, переживший смену ящика, иначе
    # запирал бы закладку новой картины навсегда.
    if SESSION.owns(key):
        return Answer(204, b"")
    phase = str(body.get("phase", ""))
    if phase not in _PHASES:
        return refusal(400, "bad_phase")
    raw_pos, raw_dur = body.get("pos", 0.0), body.get("dur", 0.0)
    if not _is_number(raw_pos) or not _is_number(raw_dur):
        return refusal(400, "bad_number")
    pos, dur = float(raw_pos), float(raw_dur)
    write_web_position(out, key=key, pos=pos, dur=dur, phase=phase, wall=CLOCK.wall())
    return Answer(204, b"")
