"""Сериал найден, а раздач нужного сезона в нём нет ни по одному имени."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeAlias

from torrcast.domain.episode import Episode
from torrcast.domain.picture import Picture

if TYPE_CHECKING:
    Args: TypeAlias = Any


def _lacks_season(found: list[Picture], args: Args) -> bool:
    """Сериал найден, а раздач нужного сезона в нём нет ни по одному имени.

    Ровно тот случай, где отбор упирался в «раздач с сезоном N нет»: TC-6 берёт сезон-пак,
    КОГДА он есть в выдаче, но у части западных сериалов («Ангел») русский запрос не
    приносит ни одной раздачи с нужным сезоном - пак лежит под оригинальным именем со
    строкой сезона (``Angel S01``), до которой русское слово не достаёт. Проверяем по
    именам (:meth:`Release.covers`), без похода в рой: имя пака сезон называет само.
    """
    tv = [p for p in found if p.kind == "tv"]
    if not tv:
        return False
    want = args.episode or Episode(1, 1)
    return not any(r.covers(want.season) for p in tv for r in p.releases)
