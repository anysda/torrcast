"""Договор приёмника: что показ о нём знает и чему приёмник должен доверять.

Отдельно от реализаций нарочно. Приёмников два - живой Chromecast
(:mod:`torrcast.cast`) и сухая заглушка (:mod:`torrcast.cast_mock`), - и обоим нужно одно
и то же: класс позиции, протокол, по которому их зовёт показ, и разбор доверенного
корня. Держать это у одной из реализаций значило бы, что вторая импортирует первую
ради трёх объявлений, а фасад :mod:`torrcast.cast` - обе, и импорт замкнулся бы в кольцо.
"""

from __future__ import annotations

from torrcast.domain.not_raised import NOT_RAISED
from torrcast.domain.position import Position
from torrcast.domain.start_refused_error import StartRefusedError
from torrcast.domain.trust_anchor import trust_anchor
from torrcast.ports.receiver import Receiver

__all__ = [
    "NOT_RAISED",
    "Position",
    "Receiver",
    "StartRefusedError",
    "trust_anchor",
]

#: Ответ подъёма «показа нет» (:meth:`torrcast.cast.ChromecastReceiver.replay`). Не ноль:
#: ноль - это законное место фильма, и показ, поднятый с самого начала картины, отвечает
#: именно им.
#:
#: 🔴 Пока «нет» и «начало картины» были одним числом, назвать удачей подъём с нуля было
#: нечем: и строка человеку, и запись в ленте говорили «приёмник показ не взял» ровно
#: тогда, когда картинка уже шла. Секунд меньше нуля у фильма не бывает - отсюда знак.
