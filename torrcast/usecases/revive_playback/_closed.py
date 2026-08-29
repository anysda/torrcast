"""Показ убрал с экрана зритель: это конец сеанса, а не авария, и подъёма тут нет.

Зовёт её держатель показа (:func:`torrcast.usecases.revive_playback._hold._hold`), и только он.
"""

from __future__ import annotations

from torrcast.domain.position import Position
from torrcast.usecases.rank._hms import _hms
from torrcast.usecases.watch import Watch


def _closed(position: Position, session_tag: str, pos: float, watch: Watch | None = None) -> bool:
    """``True`` - показ закрыл зритель, поднимать его обратно нельзя.

    Своя авария и рука человека снаружи похожи: и там, и там показа на экране больше
    нет. Различает их признак самого приёмника - что осталось на экране вместо показа
    (:func:`torrcast.adapters.chromecast.cast.viewer_closed._viewer_closed`), - и признак
    этот переживает потерю сессии, в отличие от слова о ходе показа. Ни срока, ни
    вопросов зрителю тут нет: воля человека доказывается его же действием.

    Лестница воскрешения в этой ветке не начинается вовсе, и своя авария ею
    по-прежнему чинится: закрытый с пульта показ - единственное, что мимо неё проходит.

    ``pos`` - место, на котором зритель закрыл показ: последний увиденный им кадр, а
    кадра не было - место, с которого показ заводили. Оттуда же `cast` и продолжит.

    ``watch`` - сторож позиции этого сеанса. Признак ложится в него (TC-880), чтобы
    цикл юнита (:mod:`torrcast.usecases.worker_loop`) знал: закладка на следующую серию
    сдвинута, а поднимать показ на приёмнике нельзя - сеанс кончается на месте.
    """
    if not position.closed:
        return False
    print(f"{session_tag} показ закрыт с пульта на {_hms(pos)} - поднимать не буду", flush=True)
    if watch is not None:
        watch.closed_by_remote = True
    return True
