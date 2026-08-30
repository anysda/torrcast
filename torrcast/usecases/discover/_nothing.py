"""Почему ответа нет: франшиза без нужного номера или пустая выдача."""

from __future__ import annotations

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.pick_franchise import pick_franchise
from torrcast.domain.picture import Picture


def _nothing(name: str, index: int | None, pictures: list[Picture]) -> str:
    """Почему ответа нет. Причины две, и человеку с ними делать разное.

    Прежде обе накрывались одной строкой - «такой картины во франшизе нет». Она честна
    ровно в одном случае из двух: когда франшизу нашли, а нужной части в ней не оказалось.
    В остальных выдача не содержала вообще ничего похожего на запрос («дети мужчин» - это
    ``Children of Men``, в каталоге такого имени нет вовсе), и строка про франшизу
    отправляла человека проверять номер части там, где не нашлось и самого фильма.

    Разводим по факту: спрашивали ли номер и стоит ли за ним живая франшиза.

    * франшиза есть, номера в ней нет → сколько в ней картин и что номера столько нет,
      плюс перечень того, что в ней есть, - молчаливого отказа быть не должно (TC-373);
    * во всём остальном → честное «ничего не нашлось», то есть «назови другими словами».
    """
    whole = pick_franchise(name, pictures) if index is not None else []
    if whole:
        have = ", ".join(f"{p.title} ({p.year or '?'})" for p in whole[:5])
        more = phrase("discover.franchise_more") if len(whole) > 5 else ""
        return phrase(
            "discover.franchise_no_number",
            name=name,
            total=len(whole),
            index=index,
            have=have,
            more=more,
        )
    return phrase("discover.nothing_found", name=name)
