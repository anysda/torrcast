"""Справка к меню франшизы на действующих адаптерах."""

from __future__ import annotations

from collections.abc import Iterable

from torrcast.runtime.facts_wiring import FACTS
from torrcast.usecases.facts import FactPicture, Facts


class MenuFacts(Facts):
    """Тот же фоновый добор, но с кэшем и источником всего процесса.

    Меню зовёт справку одним именем и одним аргументом; кому она ходит за описаниями и
    куда их складывает, решается здесь и один раз.

    Потолок ожидания боевой показ не называет вовсе: его считает язык
    (:func:`~torrcast.domain.facts.facts_budget.facts_budget`), потому что число волн до
    первой печати у языков разное. Названный аргументом потолок сильнее - им меряют
    зеркала и им же режут добор те, кому своя секунда дороже справки.
    """

    def __init__(
        self,
        pictures: Iterable[FactPicture],
        budget: float | None = None,
    ) -> None:
        super().__init__(pictures, budget, store=FACTS.cache, source=FACTS.blurbs)

    def answered(self, title: str, year: int | None) -> bool:
        """Ответил ли источник про эту картину; пустая справка - тоже ответ, а не молчание.

        :meth:`~torrcast.usecases.facts.Facts.ready` обе беды отдаёт одинаково - пустым
        :class:`~torrcast.domain.facts.fact.Fact`, - а они разные: у картины без статьи
        справки не будет НИКОГДА, и спрашивающему (карточка веба) надо знать, что
        переспрашивать нечего. Кэш это уже различает: ряд с отметкой ``empty`` лежит на
        полке, а неспрошенного на ней нет вовсе
        (:func:`~torrcast.domain.facts.cache_rows._cached_facts`).
        """
        return (title, year) in self.found
