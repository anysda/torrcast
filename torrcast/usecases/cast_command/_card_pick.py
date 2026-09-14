"""Показ с карточки: картина по её ключу и раздача, которую карточка уже отобрала."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.info_hash import info_hash
from torrcast.domain.not_found_error import NotFoundError

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.usecases.select._prep import _Prep
    from torrcast.usecases.select.plan import Plan


def _card_number(plans: list[Plan], args: Args, find: Callable[[list[Plan], str], int]) -> int:
    """Номер картины карточки в этом круге; пропала из круга - честный отказ, не соседка."""
    number = find(plans, args.picture)
    if not 1 <= number <= len(plans):
        raise NotFoundError(phrase("choice.card_picture_gone", asked=args.title_query))
    return number


def _card_release_note(args: Args, plan: Plan, prep: _Prep) -> None:
    """Раздача карточки не сыграла: сказать об этом и не звать дорожку чужим номером.

    Номер дорожки с карточки относится к ЕЁ раздаче. У другой под тем же номером может
    стоять другой язык, поэтому номер снимается, а озвучка выбирается сама.
    """
    if not args.card_release or info_hash(prep.release) == args.card_release:
        return
    print(phrase("choice.card_release_replaced", title=plan.picture.title))
    if isinstance(args.voice, int):
        print(phrase("choice.card_voice_dropped", voice=args.voice))
        args.voice = None
