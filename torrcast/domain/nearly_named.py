"""Имя каталога в одной букве от спрошенного; зовёт отбор картин."""

from __future__ import annotations

import os.path

from torrcast.domain.facts.settings import _NEAR_LETTERS
from torrcast.domain.picture import Picture
from torrcast.domain.slugify import slugify
from torrcast.domain.subtitles import _subtitles


def nearly_named(name: str, pictures: list[Picture]) -> str:
    """Имя каталога, отличающееся от спрошенного одной буквой; пусто - такого нет.

    🔴 TC-777. «Байки Мэтр» без последней буквы отказывал там, где «Байки Мэтра» давало
    четыре картины: имя сверялось буква в букву, и допуска ни на промах клавиши, ни на
    падеж не было вовсе. Догадка тут стоит в самом конце - её спрашивают, только когда по
    имени не нашлось НИЧЕГО, - и отвечает она лишь тогда, когда близкое имя в каталоге
    ровно одно: выбирать между двумя похожими значило бы брать картину наугад.

    🔴 Прощается буква на КОНЦЕ имени (:func:`_tail_edit`) и буква ВНУТРИ слова
    (:func:`_inside_edit`), но НЕ буква на конце слова. Граница тут не формальная, а
    смысловая: конец слова несёт падеж и число, и подмена его это другая картина, а не
    промах клавиши. «Кольца власти» - сериал 2022 года, «Кольцо власти» - фильм 2007-го,
    и различает их ровно буква окончания первого слова. Внутри же слова разниться нечему:
    «безумний» не форма слова «безумный», а описка. Цифра не прощается нигде - ни в
    конце, ни внутри: это номер части, а не буква («Час пик 3» не опечатка «Часа пик 2»,
    «Форсаж 10» не опечатка «Форсажа 11»).

    Имена берём те, по которым каталог и ищут: ключ франшизы и подзаголовок картины.
    Коротким именам не прощается ничего (:data:`_NEAR_LETTERS`) - у имени из пяти букв
    одна буква разницы это уже другое слово («Психо» и «Психи»).
    """
    wanted = slugify(name)
    if len(wanted) < _NEAR_LETTERS:
        return ""
    known: set[str] = set()
    for picture in pictures:
        known.add(picture.franchise)
        known |= _subtitles(picture)
    near = sorted(
        slug for slug in known if slug and (_tail_edit(wanted, slug) or _inside_edit(wanted, slug))
    )
    return near[0] if len(near) == 1 else ""


def _tail_edit(wanted: str, slug: str) -> bool:
    """Расходятся ли имена ровно последней буквой - лишней, отбитой или другой."""
    short, long = sorted((wanted, slug), key=len)
    if short == long or len(long) - len(short) > 1 or long[-1].isdigit():
        return False
    if len(short) == len(long):
        return short[:-1] == long[:-1]
    return long[:-1] == short


def _inside_edit(wanted: str, slug: str) -> bool:
    """Расходятся ли имена одной буквой ВНУТРИ слова - лишней, отбитой или другой.

    🔴 TC-869. «безумний макс» отказывал на непустом первом круге: одиннадцать картин
    найдено, «Безумный Макс» 1979 года среди них, а выбор пуст. Прощение края тут не
    помогает вовсе - описка стоит в шестой букве из восьми, а не в окончании.

    Место расхождения и решает. Оно обязано стоять ВНУТРИ слова: и слева, и справа от
    него должна остаться буква того же слова. Позиция на конце слова отдана
    :func:`_tail_edit` только для конца ВСЕГО имени, потому что конец слова - это
    окончание, а окончание разводит картины («кольца» и «кольцо»), а не путает клавиши.
    """
    if abs(len(wanted) - len(slug)) > 1:
        return False
    short, long = sorted((wanted, slug), key=len)
    if short == long:
        return False
    spot = len(os.path.commonprefix([short, long]))
    if len(short) == len(long):
        if short[spot + 1 :] != long[spot + 1 :] or short[spot].isdigit():
            return False
    elif short[spot:] != long[spot + 1 :]:
        return False
    return _inside_word(long, spot) and not long[spot].isdigit()


def _inside_word(name: str, spot: int) -> bool:
    """Стоит ли место ``spot`` внутри слова: соседи слева и справа - буквы того же слова."""
    return 0 < spot < len(name) - 1 and "-" not in (name[spot - 1], name[spot], name[spot + 1])


__all__ = ["nearly_named"]
