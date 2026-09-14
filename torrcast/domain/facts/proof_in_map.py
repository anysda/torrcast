"""Доказательство картины выдачи офлайн-картой: её точное имя, её тип и её год."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from torrcast.domain.facts.map_picture import MapPicture
from torrcast.domain.picture import Picture

#: Картины карты под прокатным именем (:meth:`ImdbNames.pictures`); тестам и поиску без карты
#: хватает ``lambda name: []`` - тогда правила молчат и решает сама выдача, как решала.
KnownPictures = Callable[[str], list[MapPicture]]


def proof_in_map(picture: Picture, known: KnownPictures) -> MapPicture | None:
    """Самая известная строка карты, которая называет ЭТУ картину выдачи, или ``None``.

    Доказательство - точная тройка, а не сходство: то же прокатное имя, тот же тип и тот же
    год ± 1 (раздачи датируют премьеру то фестивалем, то прокатом). Сериал выдача датирует
    сезоном, а карта - годом начала, поэтому у сериала годится любой начавшийся не позже.
    Без года картину доказать нечем: имя одно на десяток тёзок, и отличает их именно год.
    """
    if picture.kind == "other" or picture.year is None or not picture.title:
        return None
    year = picture.year
    series = picture.kind == "tv"
    rows = [
        row
        for row in known(picture.title)
        if row.series == series
        and row.year is not None
        and (row.year <= year if series else abs(row.year - year) <= 1)
    ]
    return max(rows, key=lambda row: row.votes, default=None)


def _renown(pictures: Iterable[Picture], known: KnownPictures) -> int:
    """Голоса самой известной доказанной картины среди этих; ноль - карта о них молчит."""
    proofs = [proof_in_map(picture, known) for picture in pictures]
    return max((proof.votes for proof in proofs if proof is not None), default=0)


__all__ = ["KnownPictures", "proof_in_map"]
