"""Карточка показа, отданного «На ТВ», берёт место и слово у самого ТВ, а не у закладки.

Закладка ложится на диск раз в :data:`torrcast.usecases.watch.WATCH_SECONDS`, и места
буфера ТВ в ней нет вовсе: эхо каста (:func:`web.to_tv._echo`) слово ``BUFFERING`` в неё
не несёт. Карточка Home Assistant и плёнка вкладки рисуют ``место + ход часов``, пока
слово ``playing``, - а ТВ после перемотки стоит в буфере до 20 с. Стенд 06-10-2026,
«Start over», затем +100, -240, +60: карточка ушла вперёд ТВ на 14.5 с после +100 и
отстала на 8.6 с после -240, долг не возвращался до конца прогона.

Сессия каста (:class:`web.tv_session.TvSession`) живёт в том же процессе и слышит ТВ
раз в две секунды. Пока каст про ЭТОТ показ, место - её последний доклад, а буфер ТВ
называется :data:`STALLED`: наружу это ``starting`` (Home Assistant рисует его
``BUFFERING`` и часы не крутит), но поля картины при нём остаются.

Так же называется и каст, перемотанный и ещё не услышанный: сессия забывает доклад на
перемотке, и закладка под словом ``playing`` давала опросу HA ложную игру. Стенд
06-10-2026, -240 со 129.6: опрос взял «playing 0.0» в миг перемотки, следующий - игру на
0.2 через 5.8 с, и весь буфер ушёл в ход - карточка обогнала ТВ на 4.2 с до конца прогона.

Каст «Play on TV» с карточки держит не сессия вкладки, а юнит показа, и слово ТВ о буфере он
кладёт в запись (``BUFFERING``) вместе с целью перемотки. Стенд 06-10-2026, пульт «+600»:
ТВ 14 с стоял в буфере на 719.9, а карточка шла часами от 113.7.
"""

from __future__ import annotations

from dataclasses import replace

from hass.motion import PAUSED, PLAYING
from hass.record_fresh import record_fresh
from torrcast.adapters.browser.read_web_box import read_web_box
from torrcast.domain.playback_snapshot import PlaybackSnapshot
from torrcast.usecases.playback.hls_root import hls_root
from web.tv_session import SESSION

#: Слово моста о буфере ТВ под идущим показом: наружу уходит ``starting`` (:mod:`hass.payload`).
STALLED = "stalled"
#: Слово записи показа о буфере ТВ (:func:`torrcast.usecases.revive_playback._screen._note_watch`).
BUFFERING = "BUFFERING"


def tv_heard(
    hls_dir: str, shown: PlaybackSnapshot | None, word: str
) -> tuple[PlaybackSnapshot | None, str]:
    """Снимок и слово карточки с поправкой на доклад ТВ; без каста вкладки - по записи юнита.

    Поправляется только идущий показ (``playing``/``paused``): подъём и тёмный экран -
    слова самого показа, и ТВ о них знает не больше записи.
    """
    if shown is None or word not in (PLAYING, PAUSED):
        return shown, word
    if word == PLAYING and shown.paused == BUFFERING:  # каст с карточки: слово ТВ в записи
        return shown, STALLED
    key = str(read_web_box(hls_root(hls_dir)).get("key", ""))
    if not key or not SESSION.owns(key):  # каста вкладки нет или он чужой: место - запись юнита
        return (record_fresh(shown) if word == PLAYING else shown), word
    heard = SESSION.heard(key)
    if heard is None:  # перемотан и ещё не слышан: ТВ идёт к новому месту, а не играет
        return shown, STALLED if word == PLAYING else word
    shown = replace(shown, position=heard.pos)
    return shown, STALLED if word == PLAYING and heard.state == "BUFFERING" else word
