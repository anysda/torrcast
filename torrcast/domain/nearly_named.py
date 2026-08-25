"""Имя каталога, отличающееся от спрошенного последней буквой; зовёт отбор картин."""

from __future__ import annotations

from torrcast.domain.facts.settings import _NEAR_LETTERS
from torrcast.domain.picture import Picture
from torrcast.domain.slugify import slugify
from torrcast.domain.subtitles import _subtitles


def nearly_named(name: str, pictures: list[Picture]) -> str:
    """Имя каталога, отличающееся от спрошенного последней буквой; пусто - такого нет.

    🔴 TC-777. «Байки Мэтр» без последней буквы отказывал там, где «Байки Мэтра» давало
    четыре картины: имя сверялось буква в букву, и допуска ни на промах клавиши, ни на
    падеж не было вовсе. Догадка тут стоит в самом конце - её спрашивают, только когда по
    имени не нашлось НИЧЕГО, - и отвечает она лишь тогда, когда близкое имя в каталоге
    ровно одно: выбирать между двумя похожими значило бы брать картину наугад.

    🔴 Прощается ровно ПОСЛЕДНЯЯ буква имени (:func:`_tail_edit`), а не любая. Буква
    внутри имени - это другая картина, а не описка: «Кольца власти» - сериал 2022 года,
    «Кольцо власти» - фильм 2007-го, и различает их одна буква окончания первого слова.
    Цифра в конце тоже не описка, а номер части: «Час пик 3» не опечатка «Часа пик 2».

    Имена берём те, по которым каталог и ищут: ключ франшизы и подзаголовок картины.
    Коротким именам и последняя буква не прощается (:data:`_NEAR_LETTERS`) - у имени из
    пяти букв это уже другое слово («Психо» и «Психи»).
    """
    wanted = slugify(name)
    if len(wanted) < _NEAR_LETTERS:
        return ""
    known: set[str] = set()
    for picture in pictures:
        known.add(picture.franchise)
        known |= _subtitles(picture)
    near = sorted(slug for slug in known if slug and _tail_edit(wanted, slug))
    return near[0] if len(near) == 1 else ""


def _tail_edit(wanted: str, slug: str) -> bool:
    """Расходятся ли имена ровно последней буквой - лишней, отбитой или другой."""
    short, long = sorted((wanted, slug), key=len)
    if short == long or len(long) - len(short) > 1 or long[-1].isdigit():
        return False
    if len(short) == len(long):
        return short[:-1] == long[:-1]
    return long[:-1] == short


__all__ = ["nearly_named"]
