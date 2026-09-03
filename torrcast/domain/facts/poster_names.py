"""Имена, под которыми ищется статья картины под постер; зовёт отбор статей.

Очередь имён складывает :func:`~torrcast.domain.facts.titles_for.titles_for` - она же
одна на всю справку. Тут к ней добавляется ровно одно: голова сборника.
"""

from __future__ import annotations

from typing import Final

from torrcast.domain.facts.ask import Ask
from torrcast.domain.facts.titles_for import titles_for

#: Сколько имён картины спрашивается прямой выборкой. Хвост очереди - регистровые
#: варианты, до постера не доходящие.
_NAMES: Final = 6
#: Сколько имён головы сборника берётся сверх своих: голое имя и два уточнения.
_HEAD: Final = 3


def poster_names(ask: Ask) -> list[str]:
    """Имена, под которыми ищется статья этой картины, в порядке доверия."""
    out = titles_for(ask.title, ask.year, ask.kind)[:_NAMES]
    head = _pack_head(ask.title)
    for extra in titles_for(head, ask.year, ask.kind)[:_HEAD] if head else ():
        if extra not in out:
            out.append(extra)
    return out


def _pack_head(title: str) -> str:
    """Имя первой части у сборника; это не сборник - пустая строка.

    Сборник называет себя перечнем своих частей («Матрица, Матрица: Перезагрузка,
    Матрица: Революция»), и статья у него - статья первой части. Признак тут строгий:
    голова обязана ПОВТОРИТЬСЯ дальше в названии. Без него голова отрезалась бы у
    любого названия с запятой, и «Титаник, любовь и катастрофа» получил бы статью
    кэмероновского «Титаника» - того же года, то есть мимо всякой сверки (TC-957).
    """
    head, _, rest = title.partition(",")
    head = head.strip()
    return head if head and head.casefold() in rest.casefold() else ""
