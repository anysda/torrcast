"""Строка ухода к дублёру: что не сыграло и почему берём соседа."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.choice._named import _named
from torrcast.usecases.choice.configure import _environment_port

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def understudy_note(failed: Plan, spare: Plan, why: str) -> str:
    """Одна строка про уход к тёзке (:func:`understudy`) - печатается ВСЕГДА.

    Уход к тёзке - это смена картины, то есть ровно то, о чём молчать нельзя
    (:func:`default_note`). Строка называет обе стороны с годами и причину, по которой
    первая не сыграла: без причины это выглядело бы как каприз показа, а с ней человек
    видит, что выбор был сделан за него не от лени.
    """
    return phrase(
        "choice.understudy",
        failed=_named(failed.picture),
        why=why,
        spare=_named(spare.picture),
        releases=len(spare.ranked),
    )


def _why_refused(refusal: Exception) -> str:
    """Голова отказа - без списка приговоров и без подсказки про соседей.

    В отказе есть всё: перечень осуждённых релизов, совет выбрать руками, строка
    :func:`kin_line`. В строке ухода к тёзке нужна ровно причина, потому что совет
    «выбери руками» после автоматического ухода уже неправда.
    """
    head = str(refusal).splitlines()[0]
    return _environment_port().cut(head.split(":")[0].strip(), 60)
