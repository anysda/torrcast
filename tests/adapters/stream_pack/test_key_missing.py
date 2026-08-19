"""Проверяет сверку опорного кадра в начале куска без запуска ffprobe."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from torrcast.adapters.stream_pack.key_missing import key_missing


class _Answer:
    def __init__(self, out: str) -> None:
        self.stdout = out.encode("utf-8")
        self.returncode = 0


def test_a_piece_starting_with_a_key_frame_is_not_reported_missing() -> None:
    """``K__`` в первом пакете - кусок самостоятельный, трогать его нечем."""
    assert not key_missing(Path("/кусок.ts"), run=lambda *a, **k: _Answer("K__\n"))


def test_a_piece_starting_without_a_key_frame_is_reported() -> None:
    """🔴 TC-698. Первый пакет без ``K`` - всё видео такого куска выбросит склейка."""
    assert key_missing(Path("/кусок.ts"), run=lambda *a, **k: _Answer("___\n"))


def test_a_probe_that_said_nothing_does_not_condemn_the_piece() -> None:
    """Молчание пробы - не приговор: выбрасывать готовый перекод по нему нельзя."""
    assert not key_missing(Path("/кусок.ts"), run=lambda *a, **k: _Answer(""))


def test_a_probe_that_never_ran_does_not_condemn_the_piece() -> None:
    """Нет ffprobe или он не успел - место идёт прежним путём, а не в отказ."""

    def broken(*args: Any, **kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(cmd="ffprobe", timeout=1.0)

    assert not key_missing(Path("/кусок.ts"), run=broken)
