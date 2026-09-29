"""Достоверность ответа каталога дат выхода."""

from enum import Enum


class AiredState(Enum):
    """Ответил ли TVmaze или сеть ещё ничего не сказала."""

    KNOWN = "known"
    UNKNOWN = "unknown"


__all__ = ["AiredState"]
