"""The tracker a twin stands for (:mod:`~torrcast.domain.names_twin`): its rows are its own."""

from __future__ import annotations

from typing import Final

#: What a twin's name adds to its tracker's (the installer names it so).
TWIN: Final = " names"


def twin_base(name: str) -> str:
    """The tracker a twin stands for; any other name as it is."""
    return name.removesuffix(TWIN)


__all__ = ["TWIN", "twin_base"]
