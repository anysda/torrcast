"""Соседи по слову: картины, в чьём названии короткое имя запроса лишь стоит словом."""

from __future__ import annotations

from torrcast.domain.facts.origin import Origin
from torrcast.domain.franchise_key import franchise_key
from torrcast.domain.picture import Picture
from torrcast.domain.picture_names import picture_names
from torrcast.domain.slugify import slugify


def _neighbours_only(found: list[Picture], name: str, about: Origin) -> list[Picture]:
    """Найденное без соседей по слову; одни соседи - пусто.

    🔴 Короткое имя почти всегда стоит словом внутри чужого названия, и разбор выдачи
    отдаёт запрос такому названию: когда самой картины в выдаче нет или когда у соседа
    раздач больше (:func:`~torrcast.domain.richer_namesake._richer_namesake`). Живой
    холодный экземпляр ответил одним Knaben: по «Вверх» встала «Шары вверх» (2026),
    справка знала ``Up`` 2009 года, и человек открывал карточку чужого фильма. Так же
    «Руки вверх», когда JacRed опоздал.

    Картину запроса называет её имя или имя из справки, в том числе именем франшизы
    («Тачки 2» - тоже «Тачки»). Названа хоть одна - уходят те, кого не называет ни имя, ни
    год справки ± 1. Не названа ни одна - решает год: частичное имя («Гарри Поттер») своих
    картин не подписывает, а год первой части у них есть. Нет и года - это соседи.

    Сосед - тот, в чьём имени слово запроса стоит частью. Картину, в именах которой его нет
    вовсе, индексер привёл по имени, которое разбор не сохранил: «Грязные игры / Game of
    Love (Dirty Games)» 2021 на «Dirty Games» при справке 2005 года. Соседом её назвать нечем.

    ⚠️ Мерка стоит на слове справки и без него молчит: нет оригинала, года или имя лишь
    признано похожим (``guessed``) - отличить соседа от картины нечем.
    """
    if not found or not _vouches(about):
        return found
    names = _names(name, about)
    if any(_signed(p, names) for p in found):
        return [
            p for p in found if _signed(p, names) or _near_year(p, about) or not _worded(p, names)
        ]
    if any(_near_year(p, about) for p in found):
        return found
    return [p for p in found if not _worded(p, names)]


def _asked_in(
    found: list[Picture], pictures: list[Picture], name: str, index: int | None, about: Origin
) -> list[Picture]:
    """Сама картина справки в широкой выдаче добора, когда своего по-русски не нашлось.

    Сторож счёта картин (:func:`~torrcast.usecases.discover._widened_subject._widened_subject`)
    отвергает широкий круг целиком, и на «Вверх» без самой картины в русской выдаче это
    оставляло человеку соседей. Справка же назвала картину, и если круг по её имени привёз
    раздачи с этим именем и её годом ± 1, отвечают они, а не соседи и не отказ. Найденное
    по-русски и номер части (год справки тогда про первую часть) эта ветка не трогает.
    """
    if found or index is not None or not _vouches(about):
        return []
    names = _names(name, about)
    return [p for p in pictures if _signed(p, names) and _near_year(p, about)]


def _vouches(about: Origin) -> bool:
    return bool(about.title) and about.year is not None and not about.guessed


def _names(name: str, about: Origin) -> set[str]:
    return {slugify(n) for n in (name, about.name, about.title)} - {""}


def _signed(picture: Picture, names: set[str]) -> bool:
    own = {slugify(n) for n in picture_names(picture)}
    own |= {franchise_key(n) for n in (picture.title, picture.original) if n}
    return bool(own & names)


def _worded(picture: Picture, names: set[str]) -> bool:
    return any(n in slugify(own) for own in picture_names(picture) for n in names)


def _near_year(picture: Picture, about: Origin) -> bool:
    if picture.year is None or about.year is None:
        return False
    return abs(picture.year - about.year) <= 1


__all__ = ["_asked_in", "_neighbours_only"]
