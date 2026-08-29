"""С какой секунды и какой ЛЕНТЫ начинается уже уложенный кусок, по его же голове.

Зовёт сверка укладки прогрева (:func:`torrcast.usecases.warm.verify._verify`) на каждом
куске и показ - на каждом прогретом куске, который собирается отдать
(:func:`torrcast.usecases.feed_pack.feed_segment._warm`).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final, NamedTuple

from torrcast.usecases.warm.frag_stamp import frag_stamp
from torrcast.usecases.warm.settings import HEAD_BYTES, TS_SYNC
from torrcast.usecases.warm.ts_stamp import ts_stamp

if TYPE_CHECKING:
    from pathlib import Path

#: Заголовок показа рядом с куском: без него счётчик фрагмента не перевести в секунды
#: (:func:`torrcast.usecases.warm.head_clock.head_clock`). Имя одно на прогрев и показ -
#: его кладёт сюда сам муксер (:meth:`torrcast.usecases.warm.vault.Vault.head`).
HEAD_NAME: Final = "init.mp4"
#: Имена первых боксов, по которым голова опознаётся как кусок MP4, а не как мусор.
#: ``styp`` пишет CMAF, ``moof`` - голый фрагмент без него, ``ftyp``/``free`` встречаются
#: у куска, собранного вместе с заголовком (:func:`.piece_with_head.piece_with_head`).
_MP4_HEADS: Final = frozenset({b"styp", b"moof", b"ftyp", b"free", b"sidx"})


class _Clock(NamedTuple):
    """Начало куска и то, ПО КАКОЙ ленте оно названо."""

    #: Секунда своей ленты; ``nan`` - прочесть не вышло.
    began: float
    #: Лента куска - это лента фильма (``True``, mpegts) или счётчик прогона муксера
    #: (``False``, CMAF). Сверять с сеткой фильма можно только первое.
    movie: bool


def segment_start(path: Path) -> _Clock:
    """С какой секунды какой ленты кусок начинается на самом деле.

    Читается голова уже лежащего файла, и только она: ни ffprobe, ни ffmpeg, ни единого
    обращения к раздаче. Причина не в красоте, а в месте вызова - сверка стоит на пути
    укладки куска (:func:`torrcast.usecases.warm.verify._verify`), рядом с показом, и не
    имеет права ни ждать сеть, ни поднимать процесс. Замер на куске 2.7 МБ: 0.04-0.10 мс,
    когда кусок только что записан и лежит в кэше страниц (это и есть штатный случай -
    сверяем сразу после укладки), и 0.4 мс с холодного диска против 20-40 мс у одного
    ``ffprobe``. Замер разбора CMAF на том же месте: 0.05 мс медианой против 0.02 мс у
    разбора MPEG-TS - заголовок показа читается один раз на прогон и лежит в памяти
    (:mod:`torrcast.usecases.warm.head_clock`), на кусок приходится один ``stat``.

    🔴 Ответ несёт ДВА поля, и второе важнее первого. У mpegts метка куска - это время
    фильма плюс начало ленты, одно на все заходы
    (:func:`torrcast.adapters.stream_pack.pack_origin.pack_origin`), и сверять её с сеткой
    можно прямо. У CMAF - нельзя: ``tfdt`` там считает прогон муксера, а не фильм, и один
    и тот же кусок из двух заходов несёт два разных числа
    (:func:`torrcast.usecases.warm.frag_stamp.frag_stamp`, замер настоящим ffmpeg). Пока
    ответом было одно число, эти два случая были неотличимы: ``nan`` на любом ``.m4s``
    сторож прогрева читал как «годен», а показ - как «мимо сетки» и СТИРАЛ прогретое, то
    есть прогретое на приставке не доезжало до зрителя вовсе (TC-879).

    ``nan`` - честное «не знаю»: файл не читается, не выровнен по пакетам TS, меток в
    голове нет вовсе или у фрагмента не нашлось заголовка показа. Гадать тут нельзя ни в
    одну сторону: сторож на догадке выбрасывал бы здоровые куски.
    """
    try:
        with path.open("rb") as handle:
            head = handle.read(HEAD_BYTES)
    except OSError:
        return _Clock(math.nan, movie=True)
    if head[:1] == bytes((TS_SYNC,)):
        return _Clock(ts_stamp(head), movie=True)
    if head[4:8] in _MP4_HEADS:
        return _Clock(frag_stamp(head, path.parent / HEAD_NAME), movie=False)
    # Ни пакетов TS, ни боксов MP4: разбирать нечего, но и объявлять кусок «без времени
    # фильма» не за что - мы просто не прочли его.
    return _Clock(math.nan, movie=True)
