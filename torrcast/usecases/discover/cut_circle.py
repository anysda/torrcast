"""Круг, у которого опорный источник сдался (:func:`torrcast.domain.cut_short.cut_short`).

Те же планы, что и у полного круга: показать их можно, а помнить как полный нельзя.
Метка едет самим списком, чтобы ни один вызывающий :func:`search_circle` не менял подписи.
"""

from __future__ import annotations

from torrcast.usecases.discover.told_circle import ToldCircle


class CutCircle(ToldCircle):
    """Планы урезанного круга: кэш кругов держит их коротко и на диск не пишет."""


__all__ = ["CutCircle"]
