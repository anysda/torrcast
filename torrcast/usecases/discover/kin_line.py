"""Подсказка о живых соседях по франшизе, до меню не доехавших."""

from __future__ import annotations

from typing import Final

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.franchise_name import franchise_name
from torrcast.domain.pick_franchise import pick_franchise
from torrcast.domain.picture import Picture

#: Сколько соседей по франшизе называем в строке отказа. Больше не помещается в строку, да
#: и незачем: это подсказка, а не второй список - список человек уже получит по `cast`.
KIN_SHOWN: Final = 3


def _kin(picture: Picture | None, pictures: list[Picture], shown: set[str]) -> list[Picture]:
    """Части франшизы, до меню не доехавшие, но в каталоге живые.

    Не доехать часть могла по-разному: запрос попал в свою половину двуязычной франшизы,
    или у картины не осталось ни одного релиза, прошедшего отбор. Обещать за них ничего
    нельзя - поэтому строка отказа говорит ровно «в каталоге есть», а не «возьми это».
    """
    if picture is None:
        return []
    whole = pick_franchise(franchise_name(picture.title), pictures)
    return [p for p in whole if p.key not in shown and p.key != picture.key and p.releases]


def kin_line(kin: list[Picture]) -> str:
    """«в каталоге есть Тачки 2 (2011), Тачки 3 (2017) - cast тачки 2». Пусто - молчим.

    Строка-подсказка, и только: сама другую часть не запускает. Человек просил «cast
    cars», у этой картины годного релиза не нашлось - и подменить её соседкой по франшизе
    значило бы показать не то, что просили. А вот промолчать о живых соседях, отправив
    человека разбираться руками, - это скрыть то, что мы уже знаем.
    """
    if not kin:
        return ""
    names = ", ".join(f"{p.title} ({p.year or '?'})" for p in kin[:KIN_SHOWN])
    return phrase("discover.kin_line", names=names, command=kin[0].title.casefold())
