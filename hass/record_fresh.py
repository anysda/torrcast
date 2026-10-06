"""Место идущего показа из записи юнита, досчитанное до сейчас.

Каст «Play on TV» с карточки держит юнит показа, и место ТВ мост знает только из записи, а
её сторож кладёт раз в :data:`torrcast.usecases.watch.WATCH_SECONDS`. Home Assistant рисует
``место + ход часов от СВОЕГО опроса``, и возраст записи (до 10 с) терялся: стенд 06-10-2026,
пульт «+600» с карточки - карточка 746.9 при ТВ 749.8, после «-300» 476.6 при ТВ 484.9.
Вкладка на ТВ досчитывает доклад ТВ так же (:func:`web.tv_fresh.tv_fresh`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime

from torrcast.domain.playback_snapshot import PlaybackSnapshot
from torrcast.usecases.watch import WATCH_SECONDS

#: Старше этого запись идущего показа не досчитывается, секунды: тик сторожа плюс круг
#: опроса приёмника. Запись старше - юнит не пишет, и часы за него не идут.
FRESH_SECONDS = WATCH_SECONDS + 5.0


def record_fresh(
    shown: PlaybackSnapshot, now: Callable[[], datetime] = lambda: datetime.now(UTC)
) -> PlaybackSnapshot:
    """Снимок с местом на сейчас, если запись говорит ``PLAYING``; иначе как был."""
    if shown.paused != "PLAYING" or not shown.moved or not shown.updated:
        return shown
    try:
        age = (now() - datetime.fromisoformat(shown.updated)).total_seconds()
    except ValueError:
        return shown
    place = shown.position + min(max(age, 0.0), FRESH_SECONDS)
    return replace(shown, position=min(place, shown.duration) if shown.duration > 0 else place)
