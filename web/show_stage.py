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
from torrcast.usecases.reinforce.plan_for import plan_for
from web.card_lookup import card_lookup
from web.card_warm import CARD_WARM
from web.warm_wiring import WARM

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.domain.config import Config
    from torrcast.domain.profile import Profile
    from torrcast.ports.progress.progress import Progress
    from torrcast.usecases.select.plan import Plan
    from torrcast.usecases.select_bench.bench import Bench


def _card_circle(config: Config, args: Args, progress: Progress, profile: Profile) -> list[Plan]:
    """Круг показа: у картины с карточки - круг карточки, у остальных - свой.

    Серия с карточки берёт тот же круг, переложенный под свой сезон
    (:func:`_season_circle`); сезона в нём нет - добор сезона умеет только свой поиск.
    Копия, а не общий объект: отбор переставляет планы, а кэш карточки служит дальше.
    Круг с диска идёт в показ сразу; пул в нём старый - за свежим ходит :func:`_card_renewed`.
    """
    if args.picture and args.episode is None:
        return [_detached(plan) for plan in WARM.take(args.title_query)]
    if args.picture and (season := _season_circle(config, args, profile)):
        return season
    return search_circle(config, args, progress, profile)


def _season_circle(config: Config, args: Args, profile: Profile) -> list[Plan]:
    """Согретый круг карточки под названную серию; пусто - искать своим кругом.

    Строка серии жмётся на карточке, чей круг уже согрет: второй поиск стоил показу
    5 с, а выдача та же, из которой вкладка сезона и собрала список. Пул и ступени
    отбора те же, что у поиска (:func:`plan_for`), и прочитанные хронометраж и студия
    не теряются. Картина карточки без раздач этого сезона - повод добора, и он за поиском.
    """
    plans = WARM.ready(args.title_query)
    replanned: list[Plan] = []
    for plan in plans or []:
        runtime = 0.0 if plan.runtime_estimated else plan.runtime
        own = plan_for(copy.copy(plan.picture), args, config, profile, runtime, plan.studio)
        own.kin, own.late = list(plan.kin), plan.late
        if own.picture.key == args.picture and not own.ranked:
            return []
        if own.ranked:
            replanned.append(own)
    return replanned


def _detached(plan: Plan) -> Plan:
    """План, который отбор правит, не трогая кэш: картина и списки свои, раздачи общие.

    Не глубокая копия: опоздавший индексер (:attr:`Plan.late`) держит замок живого круга,
    и ``deepcopy`` падал на нём (стенд, «cannot pickle '_thread.lock' object»).
    """
    own = copy.copy(plan)
    own.picture, own.ranked, own.kin = copy.copy(plan.picture), list(plan.ranked), list(plan.kin)
    return own


def _card_renewed(args: Args) -> Plan | None:
    """Картина карточки из круга сети: отбор по кругу карточки кончился ничем.

    Круг с диска стоял часами, и раздачи, которой в нём нет, отбор не спросит: «Рик и
    Морти» s2e1 не стартовал на нём, пока обновление не приехало. Идущее обновление
    дожидается, а нет его - круг считается тут же (:meth:`WarmCache.take_live`).
    """
    if not args.picture:
        return None
    return card_lookup(WARM.take_live(args.title_query), args.picture)[0]


def _card_picture(plans: list[Plan], key: str) -> int:
    """Номер картины по ключу карточки - тем же правилом, каким её нашла карточка."""
    return card_lookup(plans, key)[1]


def _card_bench(args: Args, fresh: Bench) -> Bench:
    """Стенд отбора, который уже греет карточка этой картины, а иначе свежий."""
    if args.picture and args.episode is None:
        return CARD_WARM.take(args.picture, fresh)
    return fresh


def show_stage() -> None:
    """Назначить показу круг, ключ и прогрев карточки; зовёт мост страницы на старте."""
    _configure_play_stage(
        PlayStage(
            circle=_card_circle,
            picture=_card_picture,
            bench=_card_bench,
            settled=CARD_WARM.settled,
            renewed=_card_renewed,
        )
    )


__all__ = ["show_stage"]
