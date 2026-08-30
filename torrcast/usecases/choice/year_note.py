"""Честная строка, когда год дефолтной картины расходится со справкой."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.slugify import slugify

if TYPE_CHECKING:
    from torrcast.domain.facts.origin import Origin
    from torrcast.usecases.select.plan import Plan


def year_note(picked: Plan, about: Origin, asked: str = "") -> str:
    """🔴 TC-199/TC-200. Честная строка, когда год дефолтной картины расходится со справкой.

    Год картины склеивается из ИМЕНИ раздачи, а имя врёт: «Оно» уезжает раздачей 2014
    года, «Медведь» - 2026-го, «Брат 2» - «Брат 2025». Гейт подмены сверял этот год со
    справкой только ВОКРУГ ДОБОРА (:func:`_second_language`), а у картины, вставшей
    дефолтом, год не сверялся нигде - и человек молча получал не тот фильм.

    Сверка та же, что у добора: независимое слово справки
    (:func:`~torrcast.usecases.passport.Passport.of`, год выдачи ей НЕ подсказан) против года
    картины, с тем же допуском ±1 год (год производства против года проката) и той же поблажкой
    ремейку - совпал оригинал, значит та же вещь, хоть годы и врозь.

    Право у строки ровно одно - сказать вслух; ни блокировать показ, ни менять год картины
    она не вправе (TC-199/TC-200 - про честность, а не про отказ). Молчим в трёх случаях,
    и все три - ограждения:

    * справка пуста или неуверенна (``about.year is None``) - латинописанное аниме, нет
      статьи, сеть легла, год в статье назван неоднозначно. Сверять нечем, и год из имени
      остаётся единственным источником: подменять его молчанием справки нельзя;
    * год картины неизвестен (``picture.year is None``) - опровергать нечего;
    * годы сошлись (±1) или это ремейк того же оригинала - решение верное, строка была бы
      шумом.
    """
    picture = picked.picture
    if about.year is None or picture.year is None:
        return ""
    if about.title and picture.original and slugify(picture.original) == slugify(about.title):
        return ""
    if abs(picture.year - about.year) <= 1:
        return ""
    if asked:
        return phrase(
            "choice.year_note_asked",
            asked=asked,
            title=picture.title,
            year=picture.year,
            known=about.year,
        )
    return phrase(
        "choice.year_note",
        title=picture.title,
        year=picture.year,
        known=about.year,
    )
