"""Дорожки закладки, чьей раздачи нет в выдаче: по магниту её записи."""

from __future__ import annotations

from collections.abc import Callable

from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.media import Media
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.usecases.select.plan import Plan
from web.heard import Heard


def kept_heard(
    media_of: Callable[[Config, Entry], Media],
    plan: Plan,
    config: Config,
    release: str,
    kept: Entry,
) -> tuple[Heard | None, bool]:
    """Дорожки закладки по магниту её записи и признак отказа инфраструктуры.

    Раздачи закладки нет в выдаче, а «Играть» всё равно продолжит её магнит мимо отбора:
    меню - её дорожки, не «ничего». Отказ роя или TorrServer - «не знаю», а не «дорожек
    нет»: карточка переспросит его через ``RETRY`` (:mod:`web.voice_lookup`).
    """
    try:
        return Heard(media_of(config, kept), plan.picture.native, (), release), False
    except TorrcastError:
        return None, True


__all__ = ["kept_heard"]
