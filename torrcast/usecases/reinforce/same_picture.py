"""Та же ли картина возглавляет выдачу после добора; зовёт гейт подмены."""

from __future__ import annotations

from torrcast.domain.facts.origin import Origin
from torrcast.domain.franchise_key import franchise_key
from torrcast.domain.picture import Picture
from torrcast.domain.slugify import slugify


def same_picture(
    before: Picture | None, after: Picture | None, about: Origin, proven: bool
) -> bool:
    """Та же ли картина возглавляет выдачу после добора.

    Год из справки - последнее слово: она отвечает про картину, которую спросили, и если
    вожак после добора другого года, значит приехал однофамилец. Справки нет - сверяем с
    годом того, за кем шли. Годов не назвал никто (сериалы часто без года) - остаётся
    франшиза: подмену она не ловит, но и врать не будет, а без года подменять по сути
    нечего - раздачи неотличимы, и кластер всё равно свёл бы их в одну картину.

    Год ± 1 - это не послабление, а разница между годом производства и годом проката:
    её раздачи путают постоянно, и на ней гейт спотыкался бы о честный добор.

    Отдельный случай - ``before is None``: русский запрос не нашёл ни одной картины, и
    сверять добор не с чем. Тогда решает происхождение названия (``proven``): справка и
    транслит говорят о том, что спросили, а вот непроверенному оригиналу из выдачи в
    пустоту веры нет - «не нашлось» честнее наугад взятого однофамильца.

    ⚠️ TC-253. Слово справки на этом пути стоит ровно столько, сколько стоит само имя, а
    сюда оно приходит уже проверенным: догадку по сходству имён («Все мы незнакомцы» →
    «Все мы убийцы») отсеивает :func:`_second_language` ДО второго захода. Здесь её
    ловить нечем - сравнить не с чем, и в этом вся суть случая.
    """
    if after is None:
        return False
    # Ремейк или переиздание с тем же оригиналом - та же картина, хоть годы и врозь:
    # справка знает «Fruits Basket» 2006, а у индексеров ремейк 2019, и это добор, а не
    # подмена. Спорит с годом только совпадение самого ОРИГИНАЛА: русское имя картину не
    # определяет, а чужой оригинал («The Climbers» против «The Ascent») год по-прежнему
    # разводит - дыру для настоящих подмен это не открывает.
    if about.title and after.original and slugify(after.original) == slugify(about.title):
        return True
    if about.year is not None and after.year is not None:
        return abs(after.year - about.year) <= 1
    if before is None:
        return proven
    if before.year is not None and after.year is not None:
        return abs(after.year - before.year) <= 1
    return franchise_key(before.title) == franchise_key(after.title)
