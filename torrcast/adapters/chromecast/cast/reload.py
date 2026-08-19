"""Повтор LOAD посреди показа: приёмник отвалился с ``IDLE/ERROR``.

Зовёт его опрос места показа, увидевший мёртвую сессию, и больше никто."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.adapters.chromecast.cast.past_deadly import _past_deadly
from torrcast.ports.journal.slot import journal

if TYPE_CHECKING:
    from torrcast.adapters.chromecast.cast.receiver_talk import _Talk


def _reload(rcv: _Talk) -> bool:
    """Повтор LOAD посреди показа: приёмник отвалился с ``IDLE/ERROR``.

    Проверенная на этом же ТВ рецептура: ровно две попытки, дальше это не наша авария.
    Грузим с ``current_time``: манифест описывает весь фильм, поэтому вернуть
    приёмник ровно туда, где он споткнулся, — это просто позиция в LOAD. Кроме одного
    случая: кусок, на котором показ уже умирал, приёмнику больше не отдаётся
    (:meth:`_past_deadly`).
    """
    if rcv._reloads >= rcv.profile.load_retries:
        return False
    rcv._reloads += 1
    at = _past_deadly(rcv, rcv._peak)
    journal().reload(pos=rcv._peak, tries=rcv._reloads, error=rcv._error_code)
    reason = f", код {rcv._error_code}" if rcv._error_code is not None else ", без кода"
    print(f"приёмник отвалился на {rcv._peak:.0f} с{reason} - повтор LOAD", flush=True)
    try:
        rcv._restart_app()  # чистое приложение: залипший молчит на любой LOAD
        rcv._load(at)
    except Exception:  # приёмник мог просто уйти - решает следующий тик
        return False
    # Перешагнули - максимум обязан уехать вместе с показом: иначе следующий нудж
    # прицелится в оставленный позади кусок, а свой же прыжок мы примем за перемотку.
    rcv._peak, rcv._nudged_to = max(rcv._peak, at), at
    return True
