"""Начало куска MPEG-TS по его голове: PTS первого пакета видео, PCR запасным ответом.

Зовёт разбор сверка уложенного (:func:`torrcast.usecases.warm.segment_start.segment_start`),
а хвостовую метку тем же ``_stamp`` берёт :func:`torrcast.usecases.warm.segment_end.segment_end`.
"""

from __future__ import annotations

import math

from torrcast.usecases.warm.settings import PCR_CLOCK, PES_CLOCK, TS_PACKET, TS_SYNC


def ts_stamp(head: bytes) -> float:
    """Секунда, с которой начинается кусок MPEG-TS; ``nan`` - разбирать нечего.

    Берётся PTS первого пакета видео. Именно PTS, а не DTS: граница сетки стоит на опорном
    кадре, а карта опорных кадров (:mod:`torrcast.domain.frames.keymap`) хранит их ВРЕМЯ
    ПОКАЗА. У релиза с B-кадрами DTS того же кадра лежит на кадр-другой раньше PTS, и
    сверка по DTS видела бы этот зазор как расхождение. Замер настоящим ffmpeg («Тачки»,
    23.976 к/с, три B-кадра, копия в CMAF): PTS первого сэмпла куска стоит на 0.125 с
    позже его же DTS на КАЖДОМ куске прогона - это 83 % порога :data:`SKEW_MAX`, то есть
    зазором тут нельзя пренебречь даже на самом спокойном релизе.

    Метки MPEG-TS абсолютные - это ``-copyts`` у обоих упаковщиков
    (:func:`torrcast.adapters.ffmpeg.pack_command.pack_command`), поэтому PTS - это время
    фильма плюс начало ленты, одно на все заходы
    (:func:`torrcast.adapters.stream_pack.pack_origin.pack_origin`); прибавляет его к границе
    сама сверка (:meth:`torrcast.usecases.warm.verify._verify`).

    PCR - запасной ответ: если в голове файла пакета видео с меткой не нашлось, начало
    берётся по часам транспорта. Он на преролл муксера раньше PTS, и порог
    (:data:`SKEW_MAX`) этот преролл вмещает.

    ``nan`` - честное «не знаю»: голова не выровнена по пакетам TS или меток в ней нет
    вовсе. Гадать тут нельзя ни в одну сторону: сторож на догадке выбрасывал бы здоровые
    куски.
    """
    pcr = math.nan
    for at in range(0, len(head) - TS_PACKET + 1, TS_PACKET):
        packet = head[at : at + TS_PACKET]
        if packet[0] != TS_SYNC:
            return math.nan  # файл не выровнен по пакетам - разбирать нечего
        payload = 4
        control = (packet[3] >> 4) & 0x3
        if control & 0x2:  # есть поле адаптации, а в нём может лежать PCR
            length = packet[4]
            if length >= 7 and packet[5] & 0x10 and math.isnan(pcr):
                base = (int.from_bytes(packet[6:10], "big") << 1) | (packet[10] >> 7)
                pcr = (base * 300 + (((packet[10] & 0x1) << 8) | packet[11])) / PCR_CLOCK
            payload = 5 + length
        if not control & 0x1 or payload + 14 > TS_PACKET or not packet[1] & 0x40:
            continue  # без содержимого, без места под заголовок PES или не начало PES
        pes = packet[payload:]
        if pes[:3] != b"\x00\x00\x01" or not 0xE0 <= pes[3] <= 0xEF or not pes[7] & 0x80:
            continue  # не видео или пакет без PTS
        return _stamp(pes[9:14])
    return pcr


def _stamp(raw: bytes) -> float:
    """Метка PES (33 бита вперемешку с маркерами) в секундах."""
    ticks = (
        ((raw[0] >> 1) & 0x7) << 30
        | raw[1] << 22
        | ((raw[2] >> 1) & 0x7F) << 15
        | raw[3] << 7
        | raw[4] >> 1
    )
    return ticks / PES_CLOCK
