"""Сериал найден, а раздач нужного сезона в нём нет ни по одному имени."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.episode import Episode
from torrcast.domain.picture import Picture

if TYPE_CHECKING:
    from torrcast.domain.args import Args


def lacks_season(found: list[Picture], args: Args, led: bool = False) -> bool:
    """Сериал найден, а раздач нужного сезона в нём нет ни по одному имени.

    Ровно тот случай, где отбор упирался в «раздач с сезоном N нет»: TC-6 берёт сезон-пак,
    КОГДА он есть в выдаче, но у части западных сериалов («Ангел») русский запрос не
    приносит ни одной раздачи с нужным сезоном - пак лежит под оригинальным именем со
    строкой сезона (``Angel S01``), до которой русское слово не достаёт. Проверяем по
    именам (:meth:`Release.covers`), без похода в рой: имя пака сезон называет само.

    ``led`` - первой стоит картина, которую узнала карта (:meth:`NamedRound.leads`). Узнан
    фильм и серию не называли - спрошен фильм, и сериал рядом с ним - сосед по слову, а не
    просьба: по «Брат 1997» в выдаче лежал «Брат Кадфаэль» (1997) с одним третьим сезоном,
    и круг ходил за «Cadfael S01» и говорил про сезон, которого никто не спрашивал.
    """
    if led and found[0].kind != "tv" and args.episode is None:
        return False
    tv = [p for p in found if p.kind == "tv"]
    if not tv:
        return False
    want = args.episode or Episode(1, 1)
    return not any(r.covers(want.season) for p in tv for r in p.releases)
