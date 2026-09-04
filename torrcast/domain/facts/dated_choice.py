"""Статьи одной картины, прошедшие сверку года; зовёт отбор статей постера.

Заходов тут ДВА, и второй идёт только по пустому месту, оставленному первым.

🔴 Порядок этот и есть та защита, которой у отдельной строки нет. «Перевыпуск»
(:func:`~torrcast.domain.facts.reissued.reissued`) - утверждение про ВСЮ картину, а не
про одну статью: год раздачи объявляется годом издания только тогда, когда своей статьи
под этот год нет ни одной. Стой второй заход рядом с первым, «Король Лев» 2019 года
получил бы картинку мультфильма 1994-го: оригинальное имя у них одно и то же, «The Lion
King», и точное совпадение имени сработало бы на старой статье - а статья своя есть у
обоих.
"""

from __future__ import annotations

from collections.abc import Sequence

from torrcast.domain.facts.ask import Ask
from torrcast.domain.facts.dated import Dated
from torrcast.domain.facts.fits_ask import fits_ask
from torrcast.domain.facts.reissued import reissued


def dated_choice(ask: Ask, rows: Sequence[Dated], known: dict[str, set[int]]) -> list[Dated]:
    """Статьи этой картины со сверенным годом; ``known`` - годы, добранные из Wikidata."""
    return [row for row in rows if fits_ask(ask, row, known)] or [
        row for row in rows if reissued(ask, row, known)
    ]
