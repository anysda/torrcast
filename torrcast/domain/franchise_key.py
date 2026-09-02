"""Правило franchise key; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.adaptationless import _adaptationless
from torrcast.domain.franchise_name import franchise_name
from torrcast.domain.slugify import slugify


def franchise_key(title: str) -> str:
    """Ключ франшизы: имя без номера части и без приметы экранизации.

    🔴 Примета экранизации снимается и ЗДЕСЬ, а не только в склейке
    (:func:`~torrcast.domain.glue.glue`). Склейка сводит картины внутри вида, франшиза
    собирает виды вместе, и починка одной стороны без другой не работает: «Sakusei
    Byoutou The Animation» вбирало живой набор в одну картину, а франшизой оставалось
    отдельной - и запрос «Sakusei Byoutou» по точному ключу попадал в соседнюю картину
    без сидов. Слово ФОРМЫ («Movie») тут снимать нельзя: им и отличается фильм от
    сериала, - а примета экранизации о виде не говорит ничего.
    """
    return _adaptationless(slugify(franchise_name(title)) or slugify(title))


__all__ = ["franchise_key"]
