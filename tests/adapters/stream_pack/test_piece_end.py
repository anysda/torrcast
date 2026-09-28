"""Конец куска по его пакетам: самая поздняя дорожка, а не опорная."""

from __future__ import annotations

import math
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from torrcast.adapters.stream_pack.piece_end import piece_end


def _probe(out: str) -> Any:
    def run(*_a: object, **_k: object) -> SimpleNamespace:
        return SimpleNamespace(stdout=out)

    return run


def test_the_end_is_the_latest_packet_of_any_track_with_its_duration() -> None:
    """Звук за картинкой - конец куска, а не обрыв: так пишет его здоровый релиз."""
    out = "1034.467000,0.041000\n1038.545333,0.021333\n1037.0,0.021\n"
    assert math.isclose(piece_end(Path("v103.ts"), run=_probe(out)), 1038.566666)


def test_a_packet_without_time_is_skipped_and_one_without_duration_still_counts() -> None:
    """``N/A`` ffprobe печатает словом: такой пакет конца не называет, но и не роняет меру."""
    out = "N/A,0.04\n12.5,N/A\n12.0,0.04\n"
    assert piece_end(Path("v1.ts"), run=_probe(out)) == 12.5


def test_an_unreadable_piece_is_an_honest_unknown() -> None:
    """Ffprobe не поднялся или ничего не сказал - ``nan``, решает вызывающий."""

    def dead(*_a: object, **_k: object) -> None:
        raise subprocess.TimeoutExpired("ffprobe", 1.0)

    assert math.isnan(piece_end(Path("v1.ts"), run=dead))
    assert math.isnan(piece_end(Path("v1.ts"), run=_probe("")))
