"""Статья названа именем франшизы, а спрошена её картина с подзаголовком."""

from __future__ import annotations

from torrcast.domain.franchise_key import franchise_key
from torrcast.domain.slugify import slugify
from torrcast.domain.split_franchise_index import split_franchise_index


def franchise_article(title: str, heading: str) -> bool:
    """Статья названа одним лишь именем франшизы, а спрошена картина с подзаголовком.

    🔴 TC-779. Раздачи подписывают картину вместе с приставкой франшизы («Тачки: Байки
    Мэтра»), а статья о ней подписана иначе («Мультачки: Байки Мэтра»). Тогда до статьи
    доходит только отрезанное начало имени - и отвечает про франшизу: «Тачки», ``Cars``,
    2006 год. Паспорт при этом ТВЁРДЫЙ, и на нём стоит всё дальнейшее: имя добора,
    которым спрашивают каталог второй раз, и год, которым гейт разводит однофамильцев.
    Спрошена была одна картина, отвечено про другую - и чем точнее названа первая, тем
    дальше уезжает ответ.

    Номер части сюда не входит: там начало имени тоже отвечает про франшизу, но имя
    латиницей у неё верное - номер к нему приставляется обратно
    (:func:`~torrcast.domain.facts.read_origin._other_part`). Подзаголовок приставить
    обратно нечем: ``Cars`` не превращается в ``Cars Toons`` ничем, кроме догадки.

    Заголовок с номером части статьёй франшизы не считается: «Один дома 2» - это уже
    картина, и подзаголовок «Затерянный в Нью-Йорке» её же и называет.
    """
    base, index = split_franchise_index(title)
    if index is not None:
        return False
    name = heading.split(" (")[0]
    key, wanted = slugify(name), slugify(base)
    if not key or not wanted or key == wanted:
        return False
    return wanted.startswith(f"{key}-") and franchise_key(name) == key


__all__ = ["franchise_article"]
