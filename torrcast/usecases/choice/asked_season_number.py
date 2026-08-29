"""Сезон, который назвал сам запрос вслух, если он один."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def asked_season_number(plans: list[Plan]) -> int | None:
    """Сезон, который назвал запрос вслух (``s1e1``), если он один; иначе ``None``.

    Те же ворота, что у :func:`~torrcast.usecases.choice.asked_season.asked_season`:
    серию запрос не называл, или названные планами сезоны расходятся, - судить по
    сезону нечем.
    """
    if not any(plan.asked_series for plan in plans):
        return None
    seasons = {plan.want.season for plan in plans if plan.want is not None}
    return next(iter(seasons)) if len(seasons) == 1 else None
