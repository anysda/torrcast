"""Круг, у которого опорный источник сдался (:func:`torrcast.domain.cut_short.cut_short`).

Те же планы, что и у полного круга: показать их можно, а помнить как полный нельзя.
Метка едет самим списком, чтобы ни один вызывающий :func:`search_circle` не менял подписи.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


class CutCircle(list["Plan"]):
    """Планы урезанного круга: кэш кругов держит их коротко и на диск не пишет."""


__all__ = ["CutCircle"]
