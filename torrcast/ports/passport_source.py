"""Спрашивает у справки паспорт картины: как её зовут в оригинале и какого она года."""

from __future__ import annotations

from typing import Protocol

from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.settings import FACTS_BUDGET


class PassportSource(Protocol):
    """Независимое мнение о картине для гейтов добора.

    За ним стоит внешний мир - статья Википедии, Wikidata и кэш на диске, - поэтому
    это порт, а не правило. Сценарию известно ровно три вещи: паспорт бывает пустым
    (:class:`~torrcast.domain.facts.origin.Origin`), тип картины подсказывается
    (``series``), а ждать ответа дольше ``budget`` нельзя - справка не вправе ни
    ронять поиск, ни задерживать его сверх обещанного.
    """

    def __call__(
        self, title: str, series: bool | None = False, budget: float = FACTS_BUDGET
    ) -> Origin: ...
