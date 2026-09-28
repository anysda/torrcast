"""Круг карточки, помнящий, ответил ли каталог целиком на каждую спрошенную строку."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.torrcast_error import TorrcastError
from web.answer import Answer
from web.circle_refusal import circle_refusal

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


class HeardCircle:
    """Круг карточки, помнящий, ответил ли каталог целиком на каждую спрошенную строку.

    Карточка спрашивает до трёх строк (:func:`web.own_plan.own_plan`), и «раздач нет»
    правдиво, только если полным был каждый из этих кругов: картина могла лежать как раз у
    того индексера, что смолчал на одной из строк.
    """

    def __init__(self, circle: Callable[[str], list[Plan]]) -> None:
        self.circle = circle
        self.said: list[bool] = []

    def __call__(self, query: str) -> list[Plan]:
        try:
            plans = self.circle(query)
        except NotFoundError as nothing:
            self.said.append(nothing.whole)
            raise
        self.said.append(bool(getattr(plans, "whole", False)))
        return plans

    @property
    def whole(self) -> bool:
        return bool(self.said) and all(self.said)

    def refusal(self, failed: TorrcastError | None) -> Answer:
        """Отказ карточки с меткой полноты круга: :func:`web.circle_refusal.circle_refusal`."""
        return circle_refusal(failed, self.whole)


__all__ = ["HeardCircle"]
