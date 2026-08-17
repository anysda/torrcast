"""Справка к меню франшизы на действующих адаптерах."""

from __future__ import annotations

from collections.abc import Iterable

from torrcast.domain.facts.settings import FACTS_BUDGET
from torrcast.runtime.facts_wiring import FACTS
from torrcast.usecases.facts import Facts


class MenuFacts(Facts):
    """Тот же фоновый добор, но с кэшем и источником всего процесса.

    Меню зовёт справку одним именем и одним аргументом; кому она ходит за описаниями и
    куда их складывает, решается здесь и один раз.
    """

    def __init__(
        self, pictures: Iterable[tuple[str, int | None]], budget: float = FACTS_BUDGET
    ) -> None:
        super().__init__(pictures, budget, store=FACTS.cache, source=FACTS.blurbs)
