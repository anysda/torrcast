"""Имя каталога, равное спрошенному целиком; зовёт добор пустой выдачи."""

from __future__ import annotations

from torrcast.domain.picture import Picture
from torrcast.domain.slugify import slugify
from torrcast.domain.subtitles import _subtitles


def exactly_named(name: str, pictures: list[Picture]) -> str:
    """Слаг имени каталога, равного спрошенному целиком; пусто - такого имени нет.

    🔴 TC-1158. Полка клала плитку, на которую карточка отвечала отказом: лента раздач
    знала «Tarung Unforgiven» 2026 года, а поиск индексеров этой же строкой - НИ ОДНОЙ,
    хотя укороченная строка «Tarung» отдавала обе его раздачи. Имя тут верное, и править
    в нём нечего: промах не в букве, а в том, что источник не берёт ВЕСЬ запрос.

    Поэтому ворота противоположны описке
    (:func:`~torrcast.domain.nearly_named.nearly_named`): там имя каталога обязано
    отличаться одной буквой, тут - совпасть ЦЕЛИКОМ. Совпадение по части имени не
    считается нигде: «Unforgiven» 1992 года из той же широкой выдачи отвечает лишь
    половине спрошенного, и брать его - та же подмена, что и взять вожака широкого пула.

    Имена берём те, по которым каталог и ищут: ключ франшизы и подзаголовок картины.
    """
    wanted = slugify(name)
    if not wanted:
        return ""
    known: set[str] = set()
    for picture in pictures:
        known.add(picture.franchise)
        known |= _subtitles(picture)
    return wanted if wanted in known else ""


__all__ = ["exactly_named"]
