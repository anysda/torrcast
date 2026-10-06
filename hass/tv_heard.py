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
"""

from __future__ import annotations

from dataclasses import replace

from hass.motion import PAUSED, PLAYING
from torrcast.adapters.browser.read_web_box import read_web_box
from torrcast.domain.playback_snapshot import PlaybackSnapshot
from torrcast.usecases.playback.hls_root import hls_root
from web.tv_session import SESSION

#: Слово моста о буфере ТВ под идущим показом: наружу уходит ``starting`` (:mod:`hass.payload`).
STALLED = "stalled"


def tv_heard(
    hls_dir: str, shown: PlaybackSnapshot | None, word: str
) -> tuple[PlaybackSnapshot | None, str]:
    """Снимок и слово карточки с поправкой на доклад ТВ; каста этого показа нет - как были.

    Поправляется только идущий показ (``playing``/``paused``): подъём и тёмный экран -
    слова самого показа, и ТВ о них знает не больше записи.
    """
    if shown is None or word not in (PLAYING, PAUSED):
        return shown, word
    key = str(read_web_box(hls_root(hls_dir)).get("key", ""))
    if not key or not SESSION.owns(key):
        return shown, word  # каста нет или он чужой
    heard = SESSION.heard(key)
    if heard is None:  # перемотан и ещё не слышан: ТВ идёт к новому месту, а не играет
        return shown, STALLED if word == PLAYING else word
    shown = replace(shown, position=heard.pos)
    return shown, STALLED if word == PLAYING and heard.state == "BUFFERING" else word
