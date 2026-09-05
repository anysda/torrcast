"""Вид картины, доказанный СОСЕДКОЙ по той же выдаче.

Имя раздачи бывает немо о сериале: `[Trix] Cyberpunk: Edgerunners (2022)` не несёт ни
сезона, ни номера серии, и разбор ставит вид «фильм» не потому, что увидел фильм, а
потому, что не увидел сериала (:func:`~torrcast.domain.parse_release_name.parse_release_name`).
Цена молчания видна зрителю: у картины вида «фильм» очереди серий нет по построению
(:mod:`torrcast.usecases.reinforce.plan_for`), и показ берёт самый крупный файл, то есть
двенадцатую серию вместо первой.

Признака в самом имени нет и взять его неоткуда. Но человек ищет КАРТИНУ, и в одной
выдаче рядом с немой раздачей лежат другие раздачи той же картины - названные сезоном.
Вид берётся у них. Ни одного лишнего похода в сеть на это не тратится: выдача уже в
руках, и разбор идёт по ней до всякой группировки.

Условий на соседку два, и оба куплены замером.

🔴 **Сезон назван ЯВНО** (``season``). Раздача, чей вид угадан голым диапазоном
(`Форсаж 1-6. Коллекция` разбирается как ``episodes=(1..6)`` при ``season=None``), права
голоса не имеет: между `Форсаж [1-4]` и `Nanatsu no Taizai OVA [1-2]` порога нет, и
заимствовать чужую догадку значит разносить её дальше. Без этого отбора коллекция
«Форсаж» получала вид сериала от собственной соседки.

🔴 **Год не спорит.** Одно имя носят и фильм, и сериал: `Ghost in the Shell` 1995 года -
полнометражный, а сериал с тем же именем вышел позже; так же устроены `Аватар` 2009-го
против «Аватара: легенды об Аанге», `Лило и Стич` против одноимённого сериала,
`Supergirl`, `Wicked City`, «Чебурашка». По одному совпадению имени таких набралось
**12 подмен на 374 именах корпуса** - больше, чем весь выигрыш. Поэтому соседка говорит
о НАШЕЙ картине только тогда, когда её год не противоречит нашему: совпал, либо года нет
у одной из сторон. Отсутствие года - отсутствие возражения, а не доказательство розни:
бесстрочная половина и датированная - одна картина, ровно так их сводит и
:func:`~torrcast.domain.anchor_years.anchor_years`. С этим условием подмен ноль, а улов
тот же.
"""

from __future__ import annotations

from dataclasses import replace

from torrcast.domain.release import Release
from torrcast.domain.slugify import slugify


def _names(release: Release) -> set[str]:
    """Слаги, которыми раздача зовёт свою картину: имя, оригинал, псевдонимы."""
    seen = (release.title, release.original, *release.aliases)
    return {slug for slug in (slugify(name) for name in seen if name) if slug}


def _voters(releases: list[Release]) -> list[tuple[set[str], int | None]]:
    """Соседки, назвавшие сезон ЯВНО: их имена картины и год."""
    return [
        (_names(release), release.year)
        for release in releases
        if release.kind == "tv" and release.season is not None
    ]


def _said_series(release: Release, voters: list[tuple[set[str], int | None]]) -> bool:
    """Сказала ли хоть одна соседка о ЭТОЙ картине: имя общее, год не спорит."""
    mine = _names(release)
    return any(
        names & mine and (release.year is None or year is None or release.year == year)
        for names, year in voters
    )


def sibling_kind(releases: list[Release]) -> list[Release]:
    """Поднять вид до сериала там, где о нём сказала соседка по той же выдаче.

    Меняется только «фильм»: вид «other» (не кино) и уже признанный сериал не трогаются.
    Список без единой соседки с явным сезоном возвращается тем же объектом - на выдаче,
    где доказывать нечем, работы не делается вовсе.
    """
    voters = _voters(releases)
    if not voters:
        return releases
    return [
        replace(release, kind="tv")
        if release.kind == "movie" and _said_series(release, voters)
        else release
        for release in releases
    ]


__all__ = ["sibling_kind"]
