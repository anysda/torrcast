"""Идёт ли показ прямо сейчас - по последней строке, которую он сам сказал в журнал.

Спрашивает отсюда одно место: ожидание картинки, у которого истёк бюджет старта
(:func:`torrcast.usecases.playback._launch._await_playing`), перед тем как гасить юнит.
Строку собирает :func:`torrcast.usecases.screen_line.screen_line`, и разбор держится
рядом с ней нарочно (см. её докстроку).
"""

from __future__ import annotations

import re

from torrcast.domain.catalogs.phrase import phrase

#: Слова приёмника, при которых на экране есть картинка. ``PAUSED`` тут не по ошибке:
#: паузу поставил зритель, кадр на экране его же и остался, а гасить такой показ - та же
#: потеря серии, что и гасить играющий. Движение указателя доказывается отдельно.
LIVE = frozenset({"PLAYING", "PAUSED"})

#: Метки в шаблоне строки, которыми ловятся её же переменные места (место, длительность,
#: слово приёмника) - независимо от того, какими словами кластер :mod:`torrcast.domain.
#: catalogs.screen` называет их на текущем языке.
_POS, _DUR, _STATE = "\x00pos\x00", "\x00dur\x00", "\x00state\x00"


def _said_pattern() -> re.Pattern[str]:
    """Разбор строки показа, собранный НА ХОДУ по текущему языку, а не при импорте.

    Строку сам собирает :func:`torrcast.usecases.screen_line.screen_line`, и слово,
    которым она отличается от строки темноты, живёт в каталоге, а не тут: заморозь этот
    разбор при импорте - и он остался бы русским под ``cast --en``, хотя сама строка,
    которую печатает показ, уже говорит по-английски.
    """
    template = phrase("screen.line", tag="", pos=_POS, dur=_DUR, state=_STATE)
    pattern = re.escape(template)
    pattern = pattern.replace(re.escape(_POS), r"(\d+):(\d\d):(\d\d)")
    pattern = pattern.replace(re.escape(_DUR), r"\d+:\d\d:\d\d")
    pattern = pattern.replace(re.escape(_STATE), r"(\S+)")
    return re.compile(pattern)


def still_playing(said: str, start: float) -> bool:
    """Идёт ли показ ПРЯМО СЕЙЧАС, судя по последней его же строке в журнале.

    🔴 TC-884, 29-08-2026. Доказательство картинки у CLI одно - флажок на диске, и оно
    терялось: каталог показа выметал посторонний код, а бюджет старта по исчерпании гасил
    юнит, ни о чём его не спросив. Показ шёл ровно пять с половиной минут, приёмник
    отвечал ``PLAYING``, запас был 665 с - и свой же ``cast`` погасил серию посреди
    просмотра. Спрашивать надо до казни, и спрашивать не «сказал ли приёмник PLAYING», а
    двинулся ли указатель.

    ``start`` - место, КУДА показ заводили: приёмник объявляет себя играющим раньше
    первого кадра и до него держит указатель на месте захода. Ушедший вперёд указатель -
    единственное, что кадр доказывает (тем же правилом живёт сам показ, см.
    :attr:`torrcast.usecases.revive_playback._screen_state._Screen.still_at`). Секунды
    сравниваются целыми: в строку они и уходят целыми (:func:`torrcast.domain._hms._hms`).
    """
    found = _said_pattern().search(said)
    if found is None:
        return False
    hours, minutes, seconds, state = found.groups()
    if state not in LIVE:
        return False
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) > int(start)
