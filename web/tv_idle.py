"""Доклад ТВ без картины: ``IDLE`` места не называет, ноль в нём - «отвечать некому».

Так же его читает и сам приёмник (:func:`torrcast.adapters.chromecast.cast.position._position`):
у мёртвой сессии позиции нет вовсе. Каст «На ТВ» брал этот ноль за место: стенд 06-10-2026,
фильм доигран до 10143.9, ТВ ушёл в ``IDLE`` - карточка встала на 0.0, эхо положило ноль в
закладку, а следующие «+600» считались от нуля: 600, 1200 при пустом экране.
"""

from __future__ import annotations

from dataclasses import replace

from torrcast.domain.position import Position

__all__ = ["tv_idle"]


def tv_idle(spot: Position, heard: Position | None, aim: tuple[float, float] | None) -> Position:
    """Доклад ``IDLE`` - на последнем услышанном месте, а после своей перемотки - на её цели.

    Слово ``IDLE`` остаётся: по нему пульт знает, что ТВ ничего не играет (:mod:`hass.tab_cast`).
    Места нет ни услышанного, ни цели - доклад как есть: это подъём каста, ноль там честен.
    """
    if spot.state != "IDLE":
        return spot
    if heard is not None:
        return replace(spot, pos=heard.pos, dur=heard.dur or spot.dur, playing=False)
    if aim is not None:
        return replace(spot, pos=aim[1], playing=False)
    return spot
