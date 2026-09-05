"""Правило free first; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.franchise_key import franchise_key
from torrcast.domain.picture import Picture
from torrcast.domain.slugify import slugify


def _free_first(rest: list[Picture], numbered: list[Picture]) -> Picture | None:
    """Кого из безномерных поставить ГОЛОВОЙ нумерованной строки; ``None`` - некого.

    🔴 TC-982. Претензий на голову две, и они разной силы. Картина, названная РОВНО
    именем франшизы, - это сама франшиза, и голову она берёт по праву. Родня, опознанная
    лишь корнем оригинала, - сосед: он попал сюда потому, что каталог подписал его тем же
    английским корнем, а не потому, что он первая часть.

    Пока обе претензии считались одной, «One Punch Man» кончался 24-минутной OVA
    «Путь к становлению героем» (1 раздача, 2015, `One Punch Man: Road to Hero`) впереди
    самого сериала (24 раздачи, тот же 2015): номер части у сериала был 2, первой части
    в строке не было, и голову отдавали первому попавшемуся из :data:`titled` - соседу.

    Слабая претензия работает только вместе с ГОДОМ: сосед раньше всей нумерованной
    строки и правда похож на её начало. Не раньше - головы нет вовсе, строку возглавляет
    её собственный номер, а сосед уходит в хвост, откуда его по-прежнему видно номером
    за ``--menu``.

    ⚠️ Голое имя эту проверку годом не проходит и проходить не должно: «сёгун s1e9» даёт
    нумерованной строкой чужую «Радость пытки 2: Садизм сегуна» (1976), и обе «Сёгун» -
    1980 и 2024 - моложе неё. Отними у голого имени право на голову - и меню возглавит
    чужая картина, у которой номер части взялся из названия.
    """
    roots = {franchise_key(p.original) for p in numbered if p.original}
    named = [p for p in rest if p.kind != "other" and slugify(p.title) == p.franchise]
    bare = {id(p) for p in named}
    titled = [
        p
        for p in rest
        if p.kind != "other"
        and (id(p) in bare or (p.original is not None and franchise_key(p.original) in roots))
    ]
    if not titled:
        return None
    anchor = min((p.year for p in numbered if p.year is not None), default=None)
    if anchor is None:
        return titled[0]
    early = [p for p in titled if p.year is not None and p.year < anchor and (not p.collection)]
    if not early:
        return named[0] if named else None
    return max(early, key=lambda p: (len(p.releases), -(p.year or 0)))


__all__ = ["_free_first"]
