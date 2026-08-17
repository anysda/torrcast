"""Отвечает, сколько головы файла греть под продолжение с середины; спрашивает прогрев."""

from __future__ import annotations

from torrcast.domain.warm_open import HEAD_OPEN, HEAD_OPEN_DEFAULT


def head_open(kind: str) -> int:
    """Сколько головы греть под продолжение с середины: у mkv её мало, у mp4 там ``moov``."""
    return HEAD_OPEN.get(kind, HEAD_OPEN_DEFAULT)
