"""Дорожка картинки и её шкала из заголовка показа (``init.mp4``), считанные один раз.

Спрашивает их разбор голого фрагмента CMAF
(:func:`torrcast.usecases.warm.frag_stamp.frag_stamp`).
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Final

from torrcast.domain.tape_scales import tape_scales
from torrcast.usecases.warm.settings import HEAD_BYTES

#: Заголовок бокса: четыре байта размера и четыре - имени.
_BOX_HEAD: Final = 8
#: Сколько боксов проходим на одном уровне, прежде чем счесть заголовок мусором.
_MAX_BOXES: Final = 64
#: Что уже прочитано: (файл, время правки, вес) -> (дорожка картинки, её шкала).
#:
#: 🔴 Кэш тут не украшение, а условие вызова. Разбор фрагмента стоит на горячем пути
#: показа (:func:`torrcast.usecases.warm.segment_start.segment_start`), и заголовок нужен ему
#: на КАЖДОМ куске: шкала живёт только в ``init.mp4``, во фрагменте её нет вовсе. Читать
#: заголовок на каждый кусок значило бы добавить туда второе открытие файла; читается он
#: один раз на заголовок, а ключ несёт время правки и вес - перепакованный показ кладёт
#: новый ``init.mp4``, и старая шкала значила бы в нём другое время.
#:
#: Замок не нужен: словарь читают и пишут нитки показа и прогрева разом, но и чтение, и
#: запись одного ключа в CPython неделимы, а худшее, что даёт гонка, - двойной разбор
#: одного и того же заголовка.
_KNOWN: Final[dict[tuple[str, int, int], tuple[int, int]]] = {}


def head_clock(init: Path) -> tuple[int, int]:
    """Номер дорожки картинки и сколько в ней тиков в секунде; ``(0, 0)`` - не прочли.

    Заголовок показа - единственное место, где шкала дорожки записана: голый фрагмент
    ``.m4s`` несёт ``moof`` со счётчиками, но ни одного описания дорожек в нём нет
    (:func:`torrcast.adapters.stream_pack.piece_with_head.piece_with_head`). Поэтому счётчик
    фрагмента без заголовка - это число без единицы измерения, и переводить его в секунды
    нечем.

    Дорожка ищется по ``hdlr``, а не по порядку в файле: порядок дорожек внутри заголовка
    не обещан никем, и опираться на него значило бы мерить картинку шкалой звука на первом
    же показе, где муксер написал их иначе (та же причина, по которой номер дорожки берут
    из ``tfhd``, а не из порядка ``traf`` - :func:`torrcast.domain.tape_spots.tape_spots`).

    ``(0, 0)`` - файла нет, он не читается или дорожки картинки в нём не нашлось.
    """
    try:
        stamp = init.stat()
        key = (str(init), stamp.st_mtime_ns, stamp.st_size)
        ready = _KNOWN.get(key)
        if ready is not None:
            return ready
        with init.open("rb") as handle:
            head = handle.read(HEAD_BYTES)
    except OSError:
        return 0, 0
    track = _picture(head)
    found = (track, tape_scales(head).get(track, 0)) if track else (0, 0)
    _KNOWN[key] = found
    return found


def _picture(head: bytes) -> int:
    """Номер дорожки картинки в заголовке; ``0`` - такой дорожки тут нет."""
    for start, end in _inside(head, 0, len(head), b"moov"):
        for at, upto in _inside(head, start, end, b"trak"):
            track = _track(head, at, upto)
            if track and _is_picture(head, at, upto):
                return track
    return 0


def _is_picture(head: bytes, at: int, end: int) -> bool:
    """Дорожка ``[at, end)`` - это картинка? Отвечает ``hdlr`` внутри её ``mdia``."""
    return any(
        head[start + 8 : start + 12] == b"vide"
        for media, upto in _inside(head, at, end, b"mdia")
        for start, _ in _inside(head, media, upto, b"hdlr")
    )


def _track(head: bytes, at: int, end: int) -> int:
    """Номер дорожки из её ``tkhd``: он лежит за парой времён, ширина которых - версия."""
    for start, _ in _inside(head, at, end, b"tkhd"):
        wide = head[start] == 1
        place = start + 4 + (16 if wide else 8)
        if place + 4 <= len(head):
            return int(struct.unpack(">I", head[place : place + 4])[0])
    return 0


def _inside(head: bytes, at: int, end: int, want: bytes) -> list[tuple[int, int]]:
    """Нутро каждого бокса ``want`` на этом уровне: пары «начало данных, конец бокса»."""
    found: list[tuple[int, int]] = []
    seen = 0
    while at + _BOX_HEAD <= end and seen < _MAX_BOXES:
        seen += 1
        size = struct.unpack(">I", head[at : at + 4])[0]
        if size < _BOX_HEAD or at + size > end:
            break
        if head[at + 4 : at + _BOX_HEAD] == want:
            found.append((at + _BOX_HEAD, at + size))
        at += size
    return found
