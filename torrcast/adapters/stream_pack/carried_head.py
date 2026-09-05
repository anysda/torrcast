"""Заголовок, который кусок уже несёт в себе; пусто - кусок голый, как все соседи.

Спрашивают его обе выкладки, отвечающие за параметры декодера, -
:func:`torrcast.adapters.stream_pack._own_head._own_head` на живом пути и
:func:`torrcast.adapters.stream_pack._warm_head._warm_head` на прогретом.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from torrcast.domain.cmaf_body import cmaf_body

if TYPE_CHECKING:
    from pathlib import Path

#: Сколько байт от начала куска хватает, чтобы увидеть его заголовок: у показа он
#: полторы тысячи байт, и читать ради этого весь кусок незачем.
_HEAD_PEEK: Final = 64 << 10


def carried_head(source: Path) -> bytes:
    """Заголовок этого куска, если он его несёт; ``b""`` - кусок голый.

    Несут его два исхода, и оба собраны муксером самостоятельным файлом: склейка
    (:func:`torrcast.adapters.stream_pack.merge_tracks.merge_tracks`) и кусок, которому
    заголовок приставила сама выкладка. Форма у обоих ровно та же, что приставляется
    впереди, - ``ftyp moov moof mdat``, - а заголовок вернее любого соседского: его
    написал тот же прогон ffmpeg, что и сам кусок, поэтому описывает он именно эти байты.

    🔴 На постоянном складе прогретого это единственный честный ответ на вопрос «чем
    уехало предыдущее место»: склад переживает и снятие показа, и перемотку, а память
    прогона - нет. Запись рядом с куском тут была бы вторым источником правды о том, что
    и так лежит в самом куске.
    """
    try:
        with source.open("rb") as fh:
            head = fh.read(_HEAD_PEEK)
    except OSError:
        return b""
    at = cmaf_body(head)
    return head[:at] if at > 0 else b""
