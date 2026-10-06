"""С какого мига верен доклад ТВ: статус опроса - ответ на ПРОШЛУЮ просьбу (:mod:`web.tv_fresh`)."""

from __future__ import annotations

from torrcast.domain.position import Position


def tv_since(before: Position | None, spot: Position, asked: float) -> float | None:
    """Миг прошлой просьбы ``asked`` для установившейся игры; переход - ``None``.

    Переход (буфер, пауза, первый доклад) отдаётся без мига: статус на нём мог прийти сам,
    и досчёт от прошлой просьбы увёл бы место вперёд ТВ.
    """
    steady = before is not None and before.state == spot.state == "PLAYING"
    return asked if steady else None
