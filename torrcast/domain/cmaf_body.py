"""Где в куске CMAF кончается заголовок и начинается сам фрагмент.

Спрашивает это склейка (:func:`torrcast.adapters.stream_pack.merge_tracks.merge_tracks`).
"""

from __future__ import annotations

import struct
from typing import Final

#: Сколько верхних боксов пройдём, прежде чем счесть файл не куском показа. Их тут
#: единицы (``ftyp``, ``moov``, ``moof``, ``mdat``), и длинная цепочка означает не
#: хитрый кусок, а мусор на входе.
MAX_TOP_BOXES: Final = 8

#: Заголовок бокса: четыре байта размера и четыре - имени.
_BOX_HEAD: Final = 8

#: Фрагмент показа начинается с описания своих сэмплов, а не с картинки.
_FRAGMENT: Final = b"moof"


def cmaf_body(head: bytes) -> int:
    """Смещение первого ``moof``; ``0`` - кусок уже голый, ``-1`` - фрагмента нет вовсе.

    🔴 Кусок сетки на CMAF - это ``moof mdat`` и ничего больше: параметры декодера
    приёмник берёт из общего заголовка показа, а не из каждого куска. Собранная заново
    склейка приезжает от муксера иначе - с полным ``ftyp moov`` впереди, - и уйти наружу
    в таком виде она не может: соседям она обязана быть ровней, иначе решать, нужен ли
    этому месту свой заголовок, будет уже не выкладка
    (:func:`torrcast.adapters.stream_pack._own_head._own_head`), а случайность муксера.

    Отмерять голову по постоянной длине нельзя: ``moov`` у разных прогонов разной длины,
    а у ``mdat`` больше четырёх гигабайт размер уезжает в 64-битное поле.
    """
    at = 0
    for _ in range(MAX_TOP_BOXES):
        if at + _BOX_HEAD > len(head):
            return -1
        size = struct.unpack(">I", head[at : at + 4])[0]
        kind = head[at + 4 : at + _BOX_HEAD]
        if kind == _FRAGMENT:
            return at
        step = _BOX_HEAD
        if size == 1:  # размер не влез в 32 бита и лежит следом за именем
            if at + 16 > len(head):
                return -1
            size = struct.unpack(">Q", head[at + _BOX_HEAD : at + 16])[0]
            step = 16
        if size < step:
            return -1
        at += size
    return -1
