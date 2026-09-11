"""Первый LOAD каста «На ТВ»: тот же контейнер, что у прямого показа, и отказ без хвоста.

Зовёт его :meth:`web.tv_session.TvSession.start`, и только он.
"""

from __future__ import annotations

import contextlib

from torrcast.domain.segment_container import SegmentContainer
from torrcast.ports.receiver import Receiver


def tv_load(
    receiver: Receiver, url: str, title: str, at: float, container: SegmentContainer | None
) -> None:
    """Позвать ``play`` приёмника ТВ так же, как его зовёт прямой показ на ТВ.

    Контейнер кусков ставится приёмнику до LOAD тем же приёмом, что и в
    :mod:`torrcast.usecases.playback._tract`: по нему приёмник выбирает подсказки формата
    (:func:`torrcast.adapters.chromecast.cast.hls_hints.hls_hints`). Без него LOAD «На ТВ»
    уходил с умолчанием приёмника (mpegts) на поток, упакованный в fmp4. ``None`` -
    контейнер не известен, и умолчание приёмника остаётся.

    🔴 ``play`` отказал - связь закрывается тут же: отказавший приёмник никто больше не
    держал, и его канал к ТВ жил до конца процесса страницы (стенд `.104` 11-09-2026: после
    «did not start the show: IDLE/ERROR» у экземпляра два канала к `.90` при пустом показе).
    """
    if container is not None and hasattr(receiver, "segment_container"):
        receiver.segment_container = container
    try:
        receiver.play(url, title, at=at)
    except BaseException:
        with contextlib.suppress(Exception):
            receiver.stop(quit_app=True)
        raise
