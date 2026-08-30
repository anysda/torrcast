"""Начало показа: LOAD с позицией и ожидание КАРТИНКИ, а не отправленной команды.

Зовёт его показ один раз за фильм или серию (:meth:`ChromecastReceiver.play`)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.start_refused_error import StartRefusedError

if TYPE_CHECKING:
    from torrcast.adapters.chromecast.cast.receiver_talk import _Talk


def _play(rcv: _Talk, url: str, title: str = "", at: float = 0.0) -> None:
    """Начать показ с секунды ``at`` и **дождаться картинки**, а не просто отправить LOAD.

    Без ожидания показ гаснет через секунду после команды: сторож снимает позицию
    сразу после ``play_media``, видит закономерный IDLE и считает, что играть нечего.

    ``at`` — это resume: манифест описывает весь фильм, поэтому продолжение с
    середины делается не перепаковкой «с нуля потока», а обычным LOAD с позицией.

    Зовётся один раз за показ. Перемотка сюда больше не приходит: приёмник видит весь
    фильм и мотает сам, а упаковка идёт следом за его запросами.
    """
    rcv._url, rcv._title = url, title or "torrcast"
    # Смерти считаются по кускам ЭТОГО фильма: следующей серии они не наследуются -
    # приёмник один на весь юнит, а сетка у каждой серии своя
    # (:func:`torrcast.usecases.playback._play._play`).
    rcv._deaths.clear()
    rcv._peak, rcv._reloads, rcv._stall_hits = at, 0, 0
    rcv._stall_at, rcv._stall_since = -1.0, 0.0
    rcv._seen, rcv._seek_since, rcv._nudged_to = -1.0, 0.0, -1.0
    rcv._blind, rcv._gone = 0, False
    budget = rcv.profile.revive_timeout if rcv._started else rcv.START_TIMEOUT
    rcv._started = True
    rcv._at = at
    rcv._load(at)
    if rcv._settle(budget):
        return
    # ⚠️ Отказ загрузки - не конец показа, а его первая смерть (:class:`StartRefusedError`):
    # приёмник в сети, и поднимать его есть чем. Хоронить показ здесь значит оставить
    # зрителя перед чёрным экраном при живом ТВ.
    raise StartRefusedError(
        phrase("chromecast_talk.tv_did_not_start", address=rcv.address, reason=rcv._why())
    )
