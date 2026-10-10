"""Сеанс, кончившийся у конца картины без отданного хвоста: обрыв, а не «досмотрено».

Зовёт его держатель показа (:func:`torrcast.usecases.revive_playback._hold._hold`) на двух
своих выходах у конца: стоящий указатель (:data:`TAIL_LIMIT`) и сдавшаяся лестница подъёма.
"""

from __future__ import annotations

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.ending_reached import ending_reached
from torrcast.usecases.feed_pack.feed import Feed
from torrcast.usecases.rank._hms import _hms
from torrcast.usecases.revive_playback._tail_served import _tail_served
from torrcast.usecases.watch import Watch


def _tail_cut(watch: Watch | None, feed: Feed, pos: float) -> bool:
    """``True`` - сеанс у конца оборван нашей упаковкой, и сторож показа это знает.

    Середина фильма и отданный хвост сюда не относятся: там конец показа решается как
    раньше. Оборванный хвост ставит закладке отметку темноты
    (:meth:`torrcast.usecases.watch.Watch.cut`), и следующий ``cast`` продолжает с места
    обрыва, а не засчитывает серию по доле.
    """
    if watch is None or not ending_reached(pos, feed.duration) or _tail_served(feed, pos):
        return False
    front, whole = _hms(feed.front(pos)), _hms(feed.duration)
    watch.cut(phrase("revive.tail_unserved", pos=_hms(pos), front=front, dur=whole))
    return True
