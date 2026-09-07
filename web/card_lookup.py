"""Какая картина круга отвечает на ключ карточки и каким номером её звать.

Правило отдельным модулем, а не строкой внутри :mod:`web.card`: спрашивают его двое -
сама карточка и её тесты, - а сходится в нём то, что расходится в продукте, имя картины
у ленты раздач и имя у поиска.
"""

from __future__ import annotations

from dataclasses import replace

from torrcast.domain.picture import Picture
from torrcast.domain.picture_names import picture_names
from torrcast.usecases.select.plan import Plan


def card_lookup(plans: list[Plan], key: str) -> tuple[Plan | None, int]:
    """Картина круга по ключу и её номер в нём; ключ ничей - ``(None, 0)``.

    🔴 Картина отвечает на ключ, собранный из ЛЮБОГО её имени. Имён у неё три, и все три
    расходятся: плитка полки зовёт картину так, как её назвала лента раздач («Better
    Days»), круг - прокатным именем каталога («Лучшие дни»), а оригинал у неё третий
    («Shao nian de ni»). Ключ полки не находился в круге НИ РАЗУ, и плитка «Новинок»
    открывала пустую карточку с одной кнопкой «Назад» - из неё нельзя было даже уйти
    стрелками, потому что фокусу больше не на что встать.

    🔴 Имя в ключе - это картина, а род и год - лишь то, что о ней вывела кластеризация,
    и вывела она их из РАЗНЫХ наборов раздач: полка кластеризует 14-дневное окно ленты,
    карточка - выдачу поиска по тому же имени. Один и тот же сериал получает от полки
    год свежего сезона, а от круга - год начала («Укрытие» 2026 против 2023), и род
    съезжает там же, где новые раздачи не назвали сезона («The Great Escape» 2016:
    полка сочла кино, круг - сериалом). Требовать совпадения обеих выведенных частей -
    значит требовать, чтобы два разных набора раздач вывели одно и то же (замер на
    стенде `.104` 07-09-2026: 12 плиток из 60 отвечали 404 ``not_found``).

    Поэтому имя обязано совпасть целиком, а из двух выведенных частей - хотя бы одна;
    совпавшая полностью картина всегда обходит съехавшую, а равные разбирает порядок
    круга. Тёзка, у которой разошлись ОБЕ части, остаётся отдельной картиной: «Похищение»
    1993 года на ключ сериала не отвечает.
    """
    best_score, best_number = 0, 0
    for number, plan in enumerate(plans, start=1):
        score = _score(plan.picture, key)
        if score > best_score:
            best_score, best_number = score, number
    if not best_number:
        return None, 0
    return plans[best_number - 1], best_number


def _score(picture: Picture, key: str) -> int:
    """Насколько картина отвечает ключу: 0 - не отвечает, больше - тем точнее.

    Ключи картины собираются тем же правилом :attr:`Picture.key`, а не сочиняются по
    строке; разбирается ключ на части одной и той же :func:`_parts` с обеих сторон, так
    что сверяются они ровно теми частями, из которых правило их и собрало.
    """
    kind, slug, year = _parts(key)
    best = 0
    for own in _keys(picture):
        own_kind, own_slug, own_year = _parts(own)
        if own_slug != slug:
            continue
        matched = (own_kind == kind) + (own_year == year)
        best = max(best, matched + 1 if matched else 0)
    return best


def _parts(key: str) -> tuple[str, str, str]:
    """Ключ на род, имя и год - в той же форме, в какой их склеил :attr:`Picture.key`."""
    kind, _, tail = key.partition(":")
    slug, _, year = tail.rpartition(":")
    return kind, slug, year


def _keys(picture: Picture) -> set[str]:
    """Ключи одной картины по всем её именам - тем же правилом :attr:`Picture.key`."""
    return {replace(picture, title=name).key for name in picture_names(picture)}


__all__ = ["card_lookup"]
