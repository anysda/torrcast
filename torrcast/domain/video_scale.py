"""Шкала дорожки картинки: ею и обязана быть собрана склейка.

Спрашивает её склейка (:func:`torrcast.adapters.stream_pack.merge_tracks.merge_tracks`).
"""

from __future__ import annotations

from torrcast.domain.tape_scales import _boxes, _number


def video_scale(head: bytes) -> int:
    """Шкала дорожки КАРТИНКИ этого заголовка; ``0`` - картинки в нём нет.

    🔴 Спрашивается это, чтобы собрать склейку той же шкалой, какой написан показ. Замер:
    показ пишет картинку шкалой 16000 тиков в секунду, а склейку тот же ffmpeg - 12288.
    Кусок со своим заголовком приёмник берёт как новое описание дорожек и читает им же
    СЛЕДУЮЩИЕ куски - то есть одна склейка чужой шкалы уводит не себя, а весь хвост показа.

    Дорожка ищется по своему ``hdlr``, а не по номеру: порядок дорожек в заголовке не
    обещан никем, и «первая - картинка» - это догадка, а не свойство файла.
    """
    for at, end in _boxes(head, 0, len(head), b"trak", (b"moov",)):
        for hat, hend in _boxes(head, at, end, b"hdlr", (b"mdia",)):
            if hend - hat >= 12 and head[hat + 8 : hat + 12] == b"vide":
                return _number(head, _boxes(head, at, end, b"mdhd", (b"mdia",)))
    return 0
