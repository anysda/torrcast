"""Опорный ли кадр, на который ссылается точка Cues: ответ по содержимому блока.

Зачем это спрашивается, если у блока есть флаг «опорный»: замер TC-639 на живом файле
(«Матрица» 1999, HDTV-ремукс) показал муксер, который ставит точку Cues на **каждый**
кластер и флаг опорности на **каждый** видеоблок - 8065 «опорных кадров» через ровно
1.251 с, тогда как настоящих IDR у фильма 830 на весь фильм (ffprobe, полный перебор
пакетов). Карта из такого индекса на 89.7 % состоит из призраков, и отличить призрака
можно только по содержимому кадра: у AVC опорный кадр - это IDR, NAL типа 5.

Ответ трёхзначный: ``None`` - по байтам не разобрать (не AVC, лейсинг блока, окно не
дотянулось до среза), и тогда решает вызывающий; молчать и гадать здесь нельзя - цена
ошибки в обе стороны уже оплачена: призрачная карта разводит сетку сегментов с потоком,
а ложный отказ от честного индекса лишает фильм сетки по опорным кадрам вовсе.
"""

from __future__ import annotations

from typing import Final

from torrcast.domain.frames.mkv.ids import BLOCK, BLOCK_GROUP, CLUSTER, SIMPLE_BLOCK
from torrcast.domain.frames.mkv.vint import vint
from torrcast.domain.frames.mkv.walk import walk
from torrcast.domain.frames.range_reader import RangeReader as Reader

#: ``CodecID`` дорожки AVC - единственный, чьи кадры мы умеем отличать по содержимому.
AVC: Final = "V_MPEG4/ISO/AVC"

#: Сколько байт от начала кластера берём на одну точку: заголовок кластера, первый блок
#: идущих перед срезом NAL (SEI у хороших файлов) и сам срез - сотни байт, запас на
#: толстые заголовки.
BLOCK_BYTES: Final = 128 << 10


def key_frame(reader: Reader, offset: int, track: int, codec: str) -> bool | None:
    """Опорный ли кадр дорожки ``track`` в кластере по абсолютному ``offset``.

    ``None`` - не разобрать, а не «не опорный». Один Range-запрос: содержимое кластера
    дальше первого блока не нужно.
    """
    if codec != AVC:
        return None
    buf = reader.read(offset, BLOCK_BYTES)
    found = walk(buf, 0, min(32, len(buf)))
    if not found or found[0][0] != CLUSTER:
        return None
    _, size, data = found[0]
    end = min(len(buf), data + size)
    for ident, block_size, block in walk(buf, data, end):
        payload = None
        if ident == SIMPLE_BLOCK:
            payload = block
        elif ident == BLOCK_GROUP:
            inner = [e for e in walk(buf, block, min(end, block + block_size)) if e[0] == BLOCK]
            payload = inner[0][2] if inner else None
        if payload is None:
            continue
        # Край окна мог лечь поперёк заголовка этого блока: идентификатор прочитался,
        # а тело уже за границей прочитанного куска. walk такую запись отдаёт нарочно
        # (по ней keys дочитывает индекс, не влезший в первый кусок), а читать по её
        # смещению нельзя. Это «не разобрать», а не призрак.
        if payload >= len(buf):
            continue
        number, after = vint(buf, payload, keep_marker=False)
        if number != track:
            continue
        return _idr(buf, after)
    return None


def _idr(buf: bytes, after: int) -> bool | None:
    """Первый срез блока - IDR (NAL тип 5) или нет; ``None``, если до среза не дошли.

    ``after`` - где у блока кончился номер дорожки: дальше два байта относительной метки
    и байт флагов, затем кадр - NAL'ы AVC с четырёхбайтовой длиной. Лейсинг (флаги 0x06)
    нам не по зубам: раскладывать кадры внутри блока ради редкой выродки - не тот случай.
    """
    if after + 3 >= len(buf):
        return None
    if buf[after + 2] & 0x06:
        return None
    pos = after + 3
    while pos + 5 <= len(buf):
        length = int.from_bytes(buf[pos : pos + 4], "big")
        if length < 1:
            break
        # Заголовок NAL читается и по краю окна: для ответа нужен один байт типа,
        # а не тело среза (IDR у длинного GOP весит сотни килобайт и не влезает в окно).
        kind = buf[pos + 4] & 0x1F
        if 1 <= kind <= 5:
            return kind == 5
        if pos + 4 + length > len(buf):
            break  # служебный NAL в окно не влез - до среза не добраться
        pos += 4 + length
    return None
