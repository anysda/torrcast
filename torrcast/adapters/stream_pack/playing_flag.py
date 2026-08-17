"""Называет путь флажка «картинка на экране»; по нему показ доказывает первый кадр."""

from __future__ import annotations

from pathlib import Path

from torrcast.domain.hls_settings import PLAYING_FLAG


def playing_flag(out: Path) -> Path:
    """Путь флажка «картинка на экране» (:data:`PLAYING_FLAG`)."""
    return out / PLAYING_FLAG
