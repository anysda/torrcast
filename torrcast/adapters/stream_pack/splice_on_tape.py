"""Ставит собранную склейку на ленту показа: её счётчики - счётчики куска, вместо которого
она уходит.

Зовут это выкладка перекодированного места (:mod:`torrcast.adapters.stream_pack._merged_out`)
и ужатия на месте (:mod:`torrcast.adapters.stream_pack._shrunk_out`).
"""

from __future__ import annotations

import struct
from typing import IO, TYPE_CHECKING, Final

from torrcast.domain.tape_scales import tape_scales
from torrcast.domain.tape_spots import tape_spots

if TYPE_CHECKING:
    from pathlib import Path

#: Сколько байт от начала куска хватает, чтобы прочитать его заголовок и первый ``moof``:
#: у показа заголовок полторы тысячи байт, ``moof`` - около пяти тысяч.
_PEEK: Final = 64 << 10
#: Заголовок бокса: четыре байта размера и четыре - имени.
_BOX_HEAD: Final = 8
#: Ширина счётчика: ``tfdt`` версии 0 несёт его в четырёх байтах, версии 1 - в восьми.
_WIDE: Final = 8
_NARROW: Final = 4
#: Потолок узкого счётчика: за ним число уже не влезает, и переписать кусок нечем.
_NARROW_MAX: Final = (1 << 32) - 1


def splice_on_tape(splice: Path, tape: Path, head: Path | None) -> bool:
    """Переставить счётчики ``splice`` на счётчики куска ``tape``; ``False`` - не вышло.

    🔴 Ради этого написано. На CMAF метки куска - не время фильма, а счётчик прогона
    (:func:`torrcast.domain.chunk_tape.tape_spots`), и склейку собирает НОВЫЙ прогон ffmpeg:
    его счётчики начинаются с нуля. Замер живого показа: соседи-копии сходятся тик в тик, а
    склейка того же места встаёт на тике 0 там, где соседи стоят на 2390016, - то есть
    уводит приёмник на 49.8 с назад, в начало ленты прогона. Проверка места ловит это верно
    и наружу такой кусок не пускает (живой промах -6204.457 / -6214.425 / -6234.362 с), и
    ровно поэтому склейка на CMAF не уезжала зрителю НИ РАЗУ.

    Сохранить счётчик входом нельзя: он не свойство пакетов, а счёт муксера. Замер: шесть
    наборов флагов ffmpeg (``-copyts`` до и после входов, ``-avoid_negative_ts disabled``,
    ``-output_ts_offset``, без ``empty_moov``) и сегментный муксер самого упаковщика - все
    восемь дали ноль. Поэтому счётчик правится в готовом файле, а не выпрашивается у ffmpeg.

    ``tape`` - кусок, ВМЕСТО которого уедет склейка: копия этого же места из своего прогона
    упаковки. Его счётчики - продолжение счётчиков соседей, и взять их надо целиком, а не
    посчитать по сетке: сосед справа продолжит счёт от них же, и вычисленное число разошлось
    бы с ним на округление.

    ``head`` - заголовок показа: у голого куска ``tape`` своей шкалы нет, она лежит там.
    🔴 Шкалы сверяются, а не предполагаются: тот же ffmpeg пишет показ шкалой 16000 тиков в
    секунду, а склейку - 12288 (замер), и счётчик, перенесённый между ними как есть, увёл бы
    картинку на 0.768 её места. Не сошлись - склейка не уходит вовсе: место идёт прежним
    путём, со швом звука, а не с уехавшей картинкой.

    Байты сэмплов не двигаются ни на один: ``tfdt`` переписывается на месте, в свою же
    ширину, поэтому смещения ``trun`` остаются верными и файл не переписывается целиком -
    у куска показа это 16-28 МБ.
    """
    marks = _first_marks(tape)
    if not marks:
        return False
    try:
        with splice.open("r+b") as fh:
            spots = _spots(fh)
            if not spots:
                return False
            if not _same_scales(fh, head, splice_at=0):
                return False
            patch = _patch(spots, marks)
            if patch is None:
                return False
            for at, raw in patch:
                fh.seek(at)
                fh.write(raw)
    except OSError:
        return False
    return True


def _first_marks(tape: Path) -> dict[int, int]:
    """Счётчик каждой дорожки куска, на ленту которого встаёт склейка."""
    try:
        with tape.open("rb") as fh:
            block = fh.read(_PEEK)
    except OSError:
        return {}
    out: dict[int, int] = {}
    for spot in tape_spots(block):
        out.setdefault(spot.track, spot.mark)
    return out


def _spots(fh: IO[bytes]) -> list[tuple[int, int, int, int]]:
    """Все счётчики склейки: ``(смещение в файле, ширина, дорожка, что стоит)``.

    Файл не читается целиком: боксы верхнего уровня обходятся по их же размерам, и
    целиком читается только ``moof`` - он мал, а рядом с ним лежит ``mdat`` на мегабайты.
    """
    found: list[tuple[int, int, int, int]] = []
    at = 0
    while True:
        fh.seek(at)
        header = fh.read(16)
        if len(header) < _BOX_HEAD:
            return found
        size = struct.unpack(">I", header[:4])[0]
        kind = header[4:_BOX_HEAD]
        if size == 1:
            if len(header) < 16:
                return found
            size = struct.unpack(">Q", header[_BOX_HEAD:16])[0]
        if size < _BOX_HEAD:
            return found
        if kind == b"moof":
            fh.seek(at)
            block = fh.read(size)
            found += [(s.at, s.width, s.track, s.mark) for s in tape_spots(block, base=at)]
        at += size


def _same_scales(fh: IO[bytes], head: Path | None, splice_at: int) -> bool:
    """Шкалы дорожек склейки и показа совпадают: иначе счётчик значит в них разное."""
    if head is None:
        return False
    try:
        with head.open("rb") as other:
            theirs = tape_scales(other.read(_PEEK))
    except OSError:
        return False
    fh.seek(splice_at)
    ours = tape_scales(fh.read(_PEEK))
    if not ours or not theirs:
        return False
    return all(theirs.get(track) == scale for track, scale in ours.items())


def _patch(
    spots: list[tuple[int, int, int, int]], marks: dict[int, int]
) -> list[tuple[int, bytes]] | None:
    """Что и куда написать; ``None`` - хоть одному счётчику новое число не по ширине.

    Считается всё до первой записи: файл, переписанный наполовину, - это кусок, у которого
    часть дорожки уехала, а часть нет, и увидеть это можно было бы только на приёмнике.
    """
    shift: dict[int, int] = {}
    out: list[tuple[int, bytes]] = []
    for at, width, track, mark in spots:
        if track not in marks:
            return None
        if track not in shift:
            shift[track] = marks[track] - mark
        raw = _retaped(mark + shift[track], width)
        if raw is None:
            return None
        out.append((at, raw))
    return out


def _retaped(mark: int, width: int) -> bytes | None:
    """Байты счётчика; ``None`` - число в свою ширину не влезает, переписывать нечем.

    ⚠️ Отказ тут обязателен и молчать о нём нельзя: узкий счётчик (``tfdt`` версии 0)
    держит 4294967295 тиков - при 48000 тиках в секунду это 24.9 часа, - и кусок, которому
    досталось бы обрезанное число, уехал бы приёмнику в начало ленты. Расширить бокс на
    месте нельзя: он вырос бы на четыре байта, а за ним лежат смещения сэмплов ``trun``.
    """
    if mark < 0:
        return None
    if width == _WIDE:
        return struct.pack(">Q", mark)
    if width == _NARROW and mark <= _NARROW_MAX:
        return struct.pack(">I", mark)
    return None
