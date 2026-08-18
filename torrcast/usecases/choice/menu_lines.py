"""Меню франшизы строками: номер, картина, год и справка о ней."""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

from torrcast.domain.outside_numbering import outside_numbering
from torrcast.usecases.choice._named import _BLURB_INDENT, _named
from torrcast.usecases.choice.configure import _environment_port

if TYPE_CHECKING:
    from torrcast.usecases.facts import Facts
    from torrcast.usecases.select._plan import _Plan


def menu_lines(plans: list[_Plan], facts: Facts | None = None, width: int = 0) -> str:
    """Список картин со справкой: номер, название с годом, рейтинг и хронометраж — в одну
    строку, описание — под ней, с отступом под номер.

    Формат такой, а не таблицей, ровно из-за узкого терминала: название бывает длинным
    («Тачки: Мультачки. Байки Мэтра»), а описание — тем более, и колонки разъехались бы
    на первой же франшизе. Отдельная строка вместо колонки ещё и читается сверху вниз:
    глаз идёт по номерам, а подробности — под ними.

    Описание переносится по словам и занимает столько строк, сколько нужно фразе (в
    восьмидесяти колонках это две-три). Раньше оно резалось по ширине терминала, и в
    меню оставался огрызок «американский компьютерно-анимационный…»: ни жанра, ни года,
    ни возможности дочитать. Место экономить тут не на чем — вопрос задаётся один раз.

    Справки нет (не приехала, сети нет, картины нет в Википедии) — печатается ровно та
    строка, что печаталась раньше, без пустых разделителей и без «не нашёл».
    """
    columns = width or _environment_port().columns()
    aside = outside_numbering([plan.picture for plan in plans])
    rows: list[str] = []
    for number, plan in enumerate(plans, start=1):
        picture = plan.picture
        fact = facts.get(picture.title, picture.year) if facts else _environment_port().fact()
        head = " · ".join(
            x for x in (_named(picture, picture.key in aside), fact.rating, fact.runtime) if x
        )
        rows.append(f"  {number}. {head}")
        if fact.about:
            rows += textwrap.wrap(
                _environment_port().shorten(fact.about),
                width=max(40, columns - 1),
                initial_indent=_BLURB_INDENT,
                subsequent_indent=_BLURB_INDENT,
                # Дефис - часть слова: «компьютерно-анимационный» рвать по нему незачем.
                break_on_hyphens=False,
            )
    return "\n".join(rows)
