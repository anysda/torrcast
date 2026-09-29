"""Тело полок на диск: целиком или никак, а легший диск показ не роняет."""

from __future__ import annotations

import contextlib
from pathlib import Path

from torrcast.adapters.filesystem.state.write_atomic import _write_atomic
from torrcast.domain.json_value import JsonValue
from torrcast.domain.torrcast_error import TorrcastError


def write_shelves(path: Path, body: dict[str, JsonValue]) -> None:
    """Записать тело целиком или не записать вовсе."""
    # диск лёг - полки просто не переживут рестарт, показу до этого дела нет
    with contextlib.suppress(TorrcastError):
        _write_atomic(path, body)


__all__ = ["write_shelves"]
