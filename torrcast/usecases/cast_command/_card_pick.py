"""Показ с карточки: картина по её ключу и раздача, которую карточка уже отобрала."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.info_hash import info_hash
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.same_series_later import same_series_later
from torrcast.domain.slugify import slugify

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.usecases.select._prep import _Prep
    from torrcast.usecases.select.plan import Plan


def _card_number(plans: list[Plan], args: Args, find: Callable[[list[Plan], str], int]) -> int:
    """Номер картины карточки в этом круге; пропала из круга - честный отказ, не соседка."""
    number = find(plans, args.picture) or _season_year(plans, args)
    if not 1 <= number <= len(plans):
        raise NotFoundError(phrase("choice.card_picture_gone", asked=args.title_query))
    return number


def _season_year(plans: list[Plan], args: Args) -> int:
    """Сериал карточки, собранный кругом под годом СЕЗОНА; нет такого - ноль.

    🔴 TC-1267. «Мажор» s5e8: карточка держит ``tv:мажор:2014``, а все раздачи выдачи
    подписаны «[2026, ...]» - годом пятого сезона, и круг собрал ``tv:мажор:2026``. Серия
    вышла, русская раздача в пуле есть, а показ отказывал «картины с карточки больше нет».
    Фильм, другое имя или год раньше - по-прежнему отказ, а не соседка.
    """
    kind, _, rest = args.picture.partition(":")
    slug, _, year = rest.rpartition(":")
    want = args.episode
    if kind != "tv" or want is None or not year.isdigit():
        return 0
    return next(
        (
            n
            for n, plan in enumerate(plans, start=1)
            if _later_season(plan, slug, int(year), args.picture_original, want.season)
            and plan.candidates(args)
        ),
        0,
    )


def _later_season(plan: Plan, slug: str, year: int, original: str, season: int) -> bool:
    """Картина круга - поздний сезон сериала карточки, а не ремейк того же имени.

    Ремейк («Доктор Кто» 1963 и 2005) делит с карточкой имя, а бывает и оригинал, поэтому
    сверх них решает счёт сезонов (:func:`same_series_later`).
    """
    picture = plan.picture
    return (
        picture.kind == "tv"
        and picture.key.split(":")[1] == slug
        and (picture.year or 0) > year
        and slugify(picture.original or "") == slugify(original)
        and same_series_later(picture, year, season)
    )


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
