"""Секунды в «ч:мм:сс»; зовут строки показа, слежения и оживления."""

from __future__ import annotations


def _hms(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"
