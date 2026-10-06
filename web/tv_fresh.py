"""Место ТВ на сейчас, а не на миг, когда приёмник его называл.

Опрос каста (:meth:`web.tv_session.TvSession._pump`) просит статус и тут же читает тот,
что уже лежит у pychromecast: просьба не ждёт ответа, и прочитанное - ответ на ПРОШЛЫЙ
опрос, на две секунды старше. Стенд 06-10-2026, каст после +60: в миг смены доклада
карточка стояла на 2.4-2.7 с позади ТВ, а к следующему - на 3.7 с.

Досчитывается только установившаяся игра: ``PLAYING`` и в этом докладе, и в прошлом. На
переходе статус мог прийти сам, без просьбы, и счёт от прошлого опроса ушёл бы вперёд ТВ, а
вперёд карточка не лечится ничем (:func:`custom_components.torrcast.mark_position.mark_position`
гасит лишь отставание). Такой доклад отдаётся как есть: его долг снимет следующий.
"""

from __future__ import annotations

from dataclasses import replace

from torrcast.domain.position import Position


def tv_fresh(spot: Position, since: float | None, now: float) -> Position:
    """Доклад, досчитанный до ``now``; без мига :func:`web.tv_since.tv_since` - как есть."""
    if since is None:
        return spot
    pos = spot.pos + max(0.0, now - since)
    return replace(spot, pos=min(pos, spot.dur) if spot.dur > 0 else pos)
