"""Длительность, которую видит карточка: настоящая, когда справка её знает, иначе прикидка.

:data:`torrcast.domain.runtime_guess.RUNTIME_GUESS` - плоская заглушка для битрейта отбора
(«фильм это два часа»), и она же ехала в карточку без разбора: «Оно» (2 ч 15 мин) показывало
«~2 Ч 0 МИН» даже когда справка (:class:`torrcast.domain.facts.fact.Fact`) уже знала настоящую
длительность. Отбор раздач эта правка не трогает - там прикидка ПРАВИЛЬНО остаётся заглушкой,
чинится только то, что видит человек (см. :func:`torrcast.usecases.reinforce._timed._timed`,
тот же выбор «справка или паспорт», но для пересборки плана целиком, не для одной строки).
"""

from __future__ import annotations

from torrcast.domain.facts.fact import Fact
from torrcast.domain.facts.minutes_of import minutes_of
from torrcast.usecases.select.plan import Plan


def display_runtime(plan: Plan, fact: Fact) -> tuple[float, bool]:
    """Длительность и её честная тильда для ответа карточки.

    Паспорт файла (``runtime_estimated`` ложно) справка не перебивает - TC-819: он мерил
    ИМЕННО эту раздачу, а справка знает только типовой хронометраж картины.
    """
    if not plan.runtime_estimated:
        return plan.runtime, False
    minutes = minutes_of(fact.runtime)
    if minutes <= 0:
        return plan.runtime, True
    return minutes * 60.0, False
