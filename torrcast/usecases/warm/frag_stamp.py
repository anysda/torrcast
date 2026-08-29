"""Начало голого фрагмента CMAF по его же голове: счётчик ленты прогона, а не время фильма.

Зовёт разбор сверка уложенного (:func:`torrcast.usecases.warm.segment_start.segment_start`).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from torrcast.domain.tape_spots import tape_spots
from torrcast.usecases.warm.head_clock import head_clock

if TYPE_CHECKING:
    from pathlib import Path


def frag_stamp(head: bytes, init: Path) -> float:
    """Секунда ЛЕНТЫ ПРОГОНА, с которой идёт картинка фрагмента; ``nan`` - не прочли.

    🔴 Это не время фильма, и назвать его временем фильма нельзя ни при каком разборе.
    Счётчик ``tfdt`` считает, сколько длительностей дорожки муксер написал за ЭТОТ прогон,
    и ноль у него стоит там, где прогон начался. Замер настоящим ffmpeg той же командой,
    что пакует показ (:func:`torrcast.adapters.ffmpeg.pack_command.pack_command`, ровная
    сетка по 4 с, копия видео): слот 12 из захода со слота 6 несёт ``tfdt`` 575575 при
    шкале 24000, то есть 23.982 с, а ТОТ ЖЕ слот 12 из захода со слота 10 несёт 191191,
    то есть 7.966 с. Один кусок фильма, два прогона - два разных числа.

    Вернуть в фрагмент время фильма нечем: ``-copyts``, ``-output_ts_offset`` и
    ``-avoid_negative_ts disabled`` до него не доезжают. Замер: те же куски, собранные с
    ``-segment_format_options movflags=cmaf:avoid_negative_ts=disabled``, вышли ПОБАЙТОВО
    теми же; отдельный фрагментированный ``mp4`` с ``-copyts -ss 24 -output_ts_offset
    0.183 -avoid_negative_ts disabled`` тоже начинается с ``tfdt`` 0. Ровно это же
    измерено с другой стороны у склейки на ленту показа
    (:func:`torrcast.adapters.stream_pack.splice_on_tape.splice_on_tape`): восемь наборов
    флагов, все восемь дали ноль.

    Поэтому число отсюда идёт наверх с пометкой «лента прогона»
    (:func:`torrcast.usecases.warm.segment_start.segment_start`), а сверять его с сеткой
    фильма имеет право только тот, кто эту ленту ИЗМЕРИЛ - как это делает выкладка живой
    упаковки (:func:`torrcast.adapters.stream_pack.run_tape.run_tape`).

    Берётся дорожка картинки, а не первая попавшаяся: у каждой дорожки счётчик свой и ноль
    свой, живой замер даёт между картинкой и звуком одного куска 10.0 с.

    ``nan`` - в голове нет ``moof`` со счётчиком картинки либо заголовок показа не прочёлся
    и переводить тики не во что (:func:`torrcast.usecases.warm.head_clock.head_clock`).
    """
    track, scale = head_clock(init)
    if not scale:
        return math.nan
    for spot in tape_spots(head):
        if spot.track == track:
            return spot.mark / scale
    return math.nan
