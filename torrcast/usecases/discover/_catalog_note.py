"""Строка каталога: каким именем каталог зовёт спрошенное слово."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.other_words import other_words
from torrcast.usecases.choice._named import _title
from torrcast.usecases.choice.enter_take import enter_take

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.usecases.select.plan import Plan


def _catalog_note(name: str, plans: list[Plan], args: Args) -> str:
    """Чем назвать картину, если спрошенного слова в её имени нет.

    🔴 TC-1064. Называется тут та картина, которую ВОЗЬМЁТ Enter
    (:func:`~torrcast.usecases.choice.enter_take.enter_take`), а не самая тяжёлая из найденных.
    Тяжесть решала своим счётом, и на «повелитель» строка называла «Константин: Повелитель
    тьмы» (21 раздача), меню открывалось «Повелителем», и он же брался: один экран называл
    три разные картины, а та, что стояла в строке каталога, не бралась никогда.

    Номер у прибора ОДИН (:class:`~torrcast.usecases.choice.take.Take`), и честные строки
    сверяются с ним же: тем и кончается расхождение, что расходятся не мнения, а числа.
    Верх меню тут не годится - он с этим номером совпадает не всегда.

    Слово в имени есть - строки нет вовсе (:func:`~torrcast.domain.other_words.other_words`):
    сказать «„тачки“ - в каталоге это „Тачки“» значит занять строку ничем.
    """
    taken = plans[enter_take(plans, args.title_query, args.pick, args.menu).number - 1].picture
    if not other_words(name, taken):
        return ""
    return phrase("discover.catalog_alias", name=name, other=_title(taken))


__all__ = ["_catalog_note"]
