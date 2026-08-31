"""Честная строка: под этим именем и годом картин две, а играет одна."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.choice._named import _title

if TYPE_CHECKING:
    from torrcast.domain.facts.origin import Origin
    from torrcast.usecases.select.plan import Plan


def namesake_note(picked: Plan, about: Origin) -> str:
    """🔴 TC-371. Честная строка: под этим именем и годом картин ДВЕ, а играет одна.

    Двусмысленность тут не наша: именем «Девять» и годом 2009 в русском прокате подписаны
    мюзикл ``Nine`` и мультфильм ``9``. Отбор выбирает картину по имени и году - обоими
    признаками они совпадают, - и в одну кучку их сводит сам каталог: больше в раздачах не
    сказано ничего. Развести такую пару разбору нечем, и это ровно тот случай, когда
    молчать нельзя: человек просил имя, получил одну из двух, а какую - решил вес кучки.

    Сказать об этом может только независимый источник, и он уже отвечает: справка знает
    обе картины и приносит их одним ответом (:func:`~torrcast.domain.facts.namesake.namesake`).
    Строка называет вторую картину так, как её подписала справка, - по этому имени человек отличит
    одну от другой и спросит точнее.

    Молчим, когда сверять нечего или не о чем:

    * тёзки того же года справка не нашла - строка была бы выдумкой;
    * год картины разошёлся со справкой (допуск ±1, как у :func:`year_note`): паспорт
      приехал про ДРУГУЮ картину, и её тёзка к выбранной отношения не имеет. Про сам
      разъезд годов человек читает своей строкой.
    """
    picture = picked.picture
    if not about.namesake or about.year is None or picture.year is None:
        return ""
    if abs(picture.year - about.year) > 1:
        return ""
    return phrase(
        "choice.namesake_two",
        title=_title(picture),
        year=picture.year,
        other=about.namesake,
    )
