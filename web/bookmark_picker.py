"""Файл отбора карточки с закладкой: тот, что покажет «Играть», а не цель плана."""

from __future__ import annotations

from collections.abc import Callable

from torrcast.domain.args import Args
from torrcast.domain.entry import Entry
from torrcast.domain.info_hash import info_hash
from torrcast.domain.magnet_hash import magnet_hash
from torrcast.domain.release import Release
from torrcast.domain.torr_file import TorrFile
from torrcast.usecases.playback.file_picker import file_picker
from torrcast.usecases.select.plan import Plan

Picker = Callable[[Plan, Release, list[TorrFile]], TorrFile]


def bookmark_picker(args: Args, kept: Entry | None) -> Picker:
    """Файл отбора карточки: в раздаче закладки - её файл, в остальном - обычный выбор.

    План карточки собран без серии, и его цель - первая серия первого сезона. Закладка
    «Отчаянных домохозяек» на s5e1 грела поэтому карту и голову s1e1, а «Играть» играл
    s5e1: на холодном старте две карты делили один рой, и своя приходила на 33-й
    секунде. Файл закладки и есть то, что покажет «Играть».
    """
    usual = file_picker(args)
    if kept is None or args.file is not None:
        return usual

    def chosen(plan: Plan, release: Release, files: list[TorrFile]) -> TorrFile:
        own = info_hash(release) == magnet_hash(kept.magnet)
        found = next((one for one in files if one.index == kept.file_idx), None) if own else None
        return found or usual(plan, release, files)

    return chosen


__all__ = ["bookmark_picker"]
