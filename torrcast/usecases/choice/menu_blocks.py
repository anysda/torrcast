"""Меню франшизы кусками: строка пункта и описание под ней."""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

from torrcast.usecases.choice._named import _BLURB_INDENT
from torrcast.usecases.choice.configure import _environment_port
from torrcast.usecases.choice.head_line import head_line

if TYPE_CHECKING:
    from torrcast.usecases.facts import Facts
    from torrcast.usecases.select.plan import Plan


def menu_blocks(plans: list[Plan], facts: Facts | None = None, width: int = 0) -> list[list[str]]:
    """Список картин кусками: у каждой картины строка пункта, а под ней - описание.

    Куском, а не сплошным списком строк, ровно потому, что строку пункта переписывают: по
    куску видно, СКОЛЬКО строк занял каждый пункт, а без этого счёта не найти на экране ту
    самую строку, в которую дописывается приехавший рейтинг.

    Формат такой, а не таблицей, из-за узкого терминала: название бывает длинным («Тачки:
    Мультачки. Байки Мэтра»), а описание - тем более, и колонки разъехались бы на первой же
    франшизе. Отдельная строка вместо колонки ещё и читается сверху вниз: глаз идёт по
    номерам, а подробности - под ними.

    Описание переносится по словам и занимает столько строк, сколько нужно фразе (в
    восьмидесяти колонках это две-три). Раньше оно резалось по ширине терминала, и в меню
    оставался огрызок «американский компьютерно-анимационный…»: ни жанра, ни года, ни
    возможности дочитать. Место экономить тут не на чем - вопрос задаётся один раз.

    Справку тут НЕ ждут ни секунды: берётся то, что УЖЕ приехало
    (:meth:`~torrcast.usecases.facts.Facts.ready`). Ждать - решение зовущего
    (:func:`~torrcast.usecases.choice._shown._shown`), и он ждёт ровно описания: они и
    решаются здесь, потому что второго шанса попасть в список у них нет. Не приехало ничего -
    печатается ровно та строка, что печаталась и раньше, без пустых разделителей и без
    «не нашёл».
    """
    columns = width or _environment_port().columns()
    blocks: list[list[str]] = []
    for number, plan in enumerate(plans, start=1):
        picture = plan.picture
        fact = facts.ready(picture.title, picture.year) if facts else _environment_port().fact()
        block = [head_line(number, picture, fact)]
        if fact.about:
            block += textwrap.wrap(
                _environment_port().shorten(fact.about),
                width=max(40, columns - 1),
                initial_indent=_BLURB_INDENT,
                subsequent_indent=_BLURB_INDENT,
                # Дефис - часть слова: «компьютерно-анимационный» рвать по нему незачем.
                break_on_hyphens=False,
            )
        blocks.append(block)
    return blocks
