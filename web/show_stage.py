"""Показ с карточки берёт круг карточки: второго круга рядом с ней не заводится.

Карточка спрашивает круг через прогрев (:data:`web.warm_wiring.WARM`), и показ,
названный её ключом, берёт оттуда же. Консольный ``cast`` и Home Assistant ключа
карточки не называют, и их круг прежний (:func:`search_circle`).
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from torrcast.usecases.cast_command.play_stage import PlayStage, _configure_play_stage
from torrcast.usecases.discover.search_circle import search_circle
from web.card_lookup import card_lookup
from web.warm_wiring import WARM

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.domain.config import Config
    from torrcast.domain.profile import Profile
    from torrcast.ports.progress.progress import Progress
    from torrcast.usecases.select.plan import Plan


def _card_circle(config: Config, args: Args, progress: Progress, profile: Profile) -> list[Plan]:
    """Круг показа: у картины с карточки - круг карточки, у остальных - свой.

    Серия, названная в запросе, меняет сам круг (добор сезона), и такой показ ищет сам.
    Копия, а не общий объект: отбор переставляет планы, а кэш карточки служит дальше.
    """
    if args.picture and args.episode is None:
        return [_detached(plan) for plan in WARM.take(args.title_query)]
    return search_circle(config, args, progress, profile)


def _detached(plan: Plan) -> Plan:
    """План, который отбор правит, не трогая кэш: картина и списки свои, раздачи общие.

    Не глубокая копия: опоздавший индексер (:attr:`Plan.late`) держит замок живого круга,
    и ``deepcopy`` падал на нём (стенд, «cannot pickle '_thread.lock' object»).
    """
    own = copy.copy(plan)
    own.picture, own.ranked, own.kin = copy.copy(plan.picture), list(plan.ranked), list(plan.kin)
    return own


def _card_picture(plans: list[Plan], key: str) -> int:
    """Номер картины по ключу карточки - тем же правилом, каким её нашла карточка."""
    return card_lookup(plans, key)[1]


def show_stage() -> None:
    """Назначить показу круг и ключ карточки; зовёт мост страницы на старте."""
    _configure_play_stage(PlayStage(circle=_card_circle, picture=_card_picture))


__all__ = ["show_stage"]
