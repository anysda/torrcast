"""Справка о картине спрашивается вместе с первым кругом, а не после него."""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable

from torrcast.domain.facts.origin import Origin
from torrcast.domain.goal_spare import GOAL

#: Имя упреждающей нитки начинается так: по нему её узнают и сторожа, и подделки в тестах.
AHEAD_THREAD = "passport-ahead-"


def _passport_ahead(ask: Callable[..., Origin], name: str) -> None:
    """Пустить справку по ``name`` в фон, пока индексеры ищут то же имя.

    Добору латиницей (:func:`~torrcast.usecases.discover._second_language._second_language`)
    справка нужна после первого круга, и раньше её там же и начинали спрашивать: круг
    кончился, и только тогда справке давали её :data:`~torrcast.domain.facts.settings.FACTS_BUDGET`.
    Статья Википедии по «Призрак в доспехах 2026» отвечает за 2.6 с, а на холодном стенде
    первый круг закрылся на +1.29, справку ждали до +2.79 и не дождались. Молчание справки
    отправило поиск вторым кругом по «Koukaku Kidoutai» ещё на 6.8 с, и тот круг сторож
    расширения всё равно отверг: ответ пришёл на +10.10 вместо +2.8.

    Добор так рано не начать: его имя достаётся из первой выдачи. А справку спрашивают
    тем же именем, что и первый круг, и она его уже знает. Нитка справки одна на имя
    (:class:`~torrcast.usecases.lookers.Lookers`), поэтому вопрос после круга не начинает
    поход заново, а ждёт уже идущий, и ждёт ровно свой прежний срок. Поиск не ждёт ни
    на сотую дольше, зато справка успевает и за время самого круга.

    Спрашиваем без подсказки типа (``series=None``): тип картины узнаётся только из
    выдачи, а этот вопрос поднимает обе нитки, и фильма, и сериала. Срок фона - цель
    поиска (:data:`~torrcast.domain.goal_spare.GOAL`): опоздавший ответ ложится в кэш
    справки и достаётся следующему поиску. Отказ справки поиск не роняет.
    """

    def look() -> None:
        with contextlib.suppress(Exception):
            ask(name, series=None, budget=GOAL)

    threading.Thread(target=look, daemon=True, name=f"{AHEAD_THREAD}{name}").start()
