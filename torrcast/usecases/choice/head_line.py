"""Строка пункта меню: номер, название с годом и украшения из справки."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.usecases.choice._named import _named

if TYPE_CHECKING:
    from torrcast.domain.facts.fact import Fact
    from torrcast.domain.picture import Picture


def head_line(number: int, picture: Picture, fact: Fact) -> str:
    """Пункт одной строкой: номер, название с годом, рейтинг и хронометраж.

    Рейтинг и хронометраж стоят тут, а не колонкой: название бывает длинным, и колонки
    разъехались бы на первой же франшизе. Справки нет - печатается ровно та строка, что
    печаталась бы без неё, без пустых разделителей и без «не нашёл».

    Строка собирается отдельно от списка потому, что её переписывают: меню печатается, не
    дожидаясь справки, а приехавшие украшения дописываются в уже показанную строку
    (:func:`~torrcast.usecases.choice._dress._dress`). Обе печати обязаны собирать её одинаково -
    иначе строка «дополнилась» бы на самом деле подменой соседнего пункта.
    """
    named = _named(picture, item=True)
    said = " · ".join(x for x in (named, fact.rating, fact.runtime) if x)
    return f"  {number}. {said}"
