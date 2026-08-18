"""Пул негоден: ни у одной картины нет раздачи, которой стоило бы играть."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.config import Config
from torrcast.domain.picture import Picture
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.usecases.choice import fitness
from torrcast.usecases.reinforce.plan_for import plan_for

if TYPE_CHECKING:
    from torrcast.domain.args import Args


def unfit_pool(
    found: list[Picture], args: Args, config: Config, profile: Profile = CAUTIOUS
) -> bool:
    """Пул негоден: ни у одной картины нет раздачи, которой стоило бы играть.

    «Стоило бы» - это :func:`fitness`, то есть уже собранные факты отбора: раздача годна
    по :func:`is_candidate`, жива по :data:`ALIVE_SEEDERS` и не старьё по
    :func:`is_dated`. Ни одного такого релиза во всём пуле - и вечер по этой выдаче не
    состоится, сколько бы строк в ней ни было.
    """
    return not any(fitness(plan_for(p, args, config, profile)) for p in found)
