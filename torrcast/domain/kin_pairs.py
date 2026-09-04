"""Правило kin_pairs; используют модели и фасады разбора имён."""

from __future__ import annotations

from collections.abc import Callable

from torrcast.domain.picture import Picture


def _kin_pairs(
    pictures: list[Picture],
    identity: Callable[[str], str],
    root: Callable[[int], int],
    *,
    named: bool,
    undated: bool = False,
) -> list[tuple[int, int]]:
    """Кандидаты в межвидовые двойники: пары, которым спросить о виде и об оригинале.

    Ведро только сводит стороны, а спрашивает их правило снаружи, и потому ведру можно
    быть шире правила: лишний кандидат отсеется тем же правилом, а не доехавший до него
    двойник не отсеется никогда.

    Ключей у стороны с оригиналом два, а не один. Правило спрашивает ОРИГИНАЛ, ключом же
    стояло только русское имя - и стороны одной картины падали в разные вёдра ровно там,
    где каталог назвал её по-русски по-разному: «One Piece» 1999 года лежит сериалом под
    именем «Большой Куш» и фильмом под именем «Ван-Пис», и до вопроса о виде эта пара не
    доезжала никогда. Русское имя ключом остаётся: у «Mater's Tall Tales» оригиналы не
    равны буквально, и сводит стороны именно оно.

    Год из ключа не выкидывается: под оригиналом «One Piece» стоят и сериал 1999 года, и
    фильм 2019-го, и без года правило слило бы их в одну картину - подмену, а не двойника.

    ``undated`` - заход для стороны, у которой года нет вовсе. Он идёт ОТДЕЛЬНО и ВТОРЫМ
    нарочно: год такая сторона занимает у соседей по оригиналу, и занять его можно, только
    если сосед один - одна картина, а не выбор из нескольких. До первого захода
    «Naruto Shippuuden» лежит двумя кучками (сериал 2007-2013 и фильм 2010-2011), после -
    одной, и примкнуть уже есть к чему. У «One Piece» кучек несколько и после первого
    захода, и там сторона без года остаётся стоять: выбирать было бы гаданием, а гадание
    стоит ложной склейки.
    """
    buckets: dict[tuple[str, int], list[int]] = {}
    for spot, picture in enumerate(pictures):
        year = picture.year
        if bool(picture.original) is not named or (year is None and not undated):
            continue
        if year is not None and not undated:
            buckets.setdefault((identity(picture.title), year), []).append(spot)
        if picture.original is not None:
            origin = identity(picture.original)
            borrowed = {year} if year is not None else _lone_kin(pictures, identity, root, spot)
            for found in borrowed:
                buckets.setdefault((origin, found), []).append(spot)
    return [
        (one, other)
        for same in buckets.values()
        for place, one in enumerate(same)
        for other in same[place + 1 :]
    ]


def _lone_kin(
    pictures: list[Picture],
    identity: Callable[[str], str],
    root: Callable[[int], int],
    spot: int,
) -> set[int]:
    """Годы соседей по оригиналу - и только если занимать год этой стороне есть зачем.

    Года нет не у стороны, а у КАРТИНЫ: кучка, к которой сторона уже прилипла, могла
    свой год назвать сама, и тогда занимать чужой не нужно и опасно. Пачка «Steins;Gate
    Complete Series» лежит в сериале 2011 года, а оригиналом каталог подписал ей фильм
    «Fuka Ryouiki no Deja vu», - и, заняв год фильма, сериал утащил бы фильм к себе в пул.

    Второе условие - сосед один: под оригиналом стоит одна уже сведённая картина, а не
    выбор из нескольких. Выбирать было бы гаданием, а гадание стоит ложной склейки.
    """
    if any(pictures[other].year is not None for other in _group(root, len(pictures), spot)):
        return set()
    origin = identity(pictures[spot].original or "")
    neighbours = [
        other
        for other, picture in enumerate(pictures)
        if picture.original and picture.year is not None and identity(picture.original) == origin
    ]
    if len({root(other) for other in neighbours}) != 1:
        return set()
    return {year for other in neighbours if (year := pictures[other].year) is not None}


def _group(root: Callable[[int], int], total: int, spot: int) -> list[int]:
    """Все места одной кучки со склейкой, какой она собрана к этой минуте."""
    mine = root(spot)
    return [other for other in range(total) if root(other) == mine]


__all__ = ["_kin_pairs"]
