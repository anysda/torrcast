"""Круг, где ответил не каждый спрошенный индексер."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.usecases.discover.cut_circle import CutCircle
from torrcast.usecases.discover.told_circle import ToldCircle

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def parted(plans: list[Plan]) -> bool:
    """A circle some asked indexer did not answer: cut short, silent, or refusing.

    One Prowlarr took out of reach was not asked, and it does not make the circle part.
    """
    return isinstance(plans, CutCircle) or (isinstance(plans, ToldCircle) and not plans.heard)


__all__ = ["parted"]
