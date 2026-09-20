"""Смотренная картина - первым экраном: единственный новый признак карточки TC-1329.

Испытание с «Призрак в доспехах» нашло картину СЕМНАДЦАТОЙ из семнадцати: до неё не
долистали, хотя запись о ней уже лежала в состоянии показа - зритель начинал её
смотреть через продукт. Признак ровно один - запись найдена по тому же ключу, каким её
узнаёт резюме показа (:attr:`torrcast.domain.picture.Picture.key`), - и трогает он не
порядок находок круга (:func:`torrcast.usecases.discover.search_circle.search_circle`,
дефолт :func:`~torrcast.usecases.choice.enter_take.enter_take`), а только то, что человек
ВИДИТ первым в готовой выдаче: номер ``pick`` и метка ``default`` остаются там же, где их
поставил круг и приговор ``enter_take`` (:func:`hass.search_results.search_results`), -
переставляются только сами записи.

Досмотрена картина до конца или нет, роли не играет: запись в состоянии значит «через
torrcast её уже смотрели», а не «досматривают прямо сейчас» - это разные вопросы
(:attr:`torrcast.domain.entry.Entry.watched` отвечает на второй, тут он не спрашивается).
Несколько смотренных картин в одной выдаче - все встают первыми, порядок между ними
остаётся таким, каким был до перестановки. Истории нет вовсе, ни одна находка ей не
отвечает, или хранилище состояния вовсе не собрано (:mod:`tests.hass_integration`
строит тело ответа серве в обход композиционного корня, минуя
:func:`torrcast.runtime.wire.wire`) - выдача не меняется ни одной перестановкой.
"""

from __future__ import annotations

from torrcast.domain.json_value import JsonValue
from torrcast.ports.state_store.slot import store


def watched_first(hits: list[JsonValue]) -> list[JsonValue]:
    """Смотренные записи - в начало списка, остальной порядок как был (устойчиво)."""
    try:
        state = store()
    except RuntimeError:
        # Хранилища нет вовсе - признака взять неоткуда, а не отказ всей выдачи.
        return hits
    seen = state.load().entries
    watched = [hit for hit in hits if isinstance(hit, dict) and hit.get("key") in seen]
    rest = [hit for hit in hits if not (isinstance(hit, dict) and hit.get("key") in seen)]
    return watched + rest


__all__ = ["watched_first"]
