"""Серия, которую юнит доиграет следом за только что досмотренной.

Спрашивают её и цикл юнита (:mod:`torrcast.usecases.worker_loop`), и сам показ
(:mod:`torrcast.usecases.playback`): между ними она и стояла кольцом.
"""

from __future__ import annotations

from torrcast.domain.entry import Entry
from torrcast.ports.module import module

#: Состояние показа - внешний мир, и сценарий зовёт его по имени, а не импортом.
State = module("torrcast.adapters.filesystem.state").State


def _following(key: str) -> Entry | None:
    """Серия, которую юнит доиграет следом за только что досмотренной.

    ``None`` — показ на этом кончается: фильм, последняя серия сезона или запись, которую
    сериалом и не считали. Отсюда же знают, закрывать ли приложение приёмника: между
    сериями оно живёт дальше, а на конце показа — гаснет (см. :func:`_play`).
    """
    entry: Entry | None = State.load().get(key)
    if entry is None or entry.done or not entry.label:
        return None
    return entry
