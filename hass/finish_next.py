"""Штатный конец серии, выбранный маршрутом ``POST /api/next``."""

from __future__ import annotations

from collections.abc import Callable

from hass.motion import Motion
from hass.next_show import next_show
from hass.refused_error import BUSY, RefusedError
from hass.say import SEEKBY
from hass.tab_finish import tab_finish
from torrcast.adapters.browser.read_web_box import read_web_box
from torrcast.domain.config import Config
from torrcast.domain.json_value import JsonValue
from torrcast.ports.playback_session import PlaybackSession
from torrcast.usecases.playback.hls_root import hls_root
from web.tv_session import SESSION


def finish_next(
    session: PlaybackSession,
    body: dict[str, JsonValue],
    settings: Callable[[], Config],
    control: Callable[[str, float], None],
    motion: Motion,
) -> None:
    """Закончить живую серию без второго запуска; запоздалый зов ничего не делает.

    Вкладке уходит её команда конца (:func:`hass.tab_finish.tab_finish`), остальным - перемотка
    к секунде перед концом. Каст «На ТВ» перематывает от места ТВ, и остаток тогда считает
    он сам (:meth:`web.tv_session.TvSession.left`), а не снимок моста.
    """
    if not next_show(session, body):
        return
    shown = session.snapshot(session.key())
    if shown is None or shown.duration <= 0:
        raise RefusedError(BUSY)
    left = max(0.0, shown.duration - shown.position - 1.0)
    config = settings()
    if tab_finish(config, shown.duration - 1.0):
        motion.commanded(SEEKBY, left)
    else:
        key = str(read_web_box(hls_root(config.hls_dir)).get("key", ""))
        on_tv = SESSION.left(key, shown.duration) if key else None
        control(SEEKBY, left if on_tv is None else on_tv)
