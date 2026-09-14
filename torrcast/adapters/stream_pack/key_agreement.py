"""Вердикт сверки карты и признак настоящего измерения пробным прогоном."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class KeyAgreement:
    """Согласие карты с файлом и отдельная правда о том, что факт был измерен."""

    agreed: bool
    measured: bool

    def __bool__(self) -> bool:
        return self.agreed


__all__ = ["KeyAgreement"]
