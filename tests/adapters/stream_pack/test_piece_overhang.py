"""Звук за картинкой в готовом куске: по его пакетам, а не по списку нарезки."""

from __future__ import annotations

import math
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from torrcast.adapters.stream_pack.piece_overhang import piece_overhang


def _probe(out: str, seen: list[list[str]] | None = None) -> Any:
    def run(command: list[str], *_a: object, **_k: object) -> SimpleNamespace:
        if seen is not None:
            seen.append(command)
        return SimpleNamespace(stdout=out)

    return run


def test_sound_past_the_last_frame_is_the_overhang_with_its_duration() -> None:
    """Замер «Теория большого взрыва» s2e5: видео до 14.681, звук до 15.573 в своём куске."""
    out = "video,14.639000,0.041688\naudio,15.552000,0.021333\naudio,15.0,0.021\n"
    assert math.isclose(piece_overhang(Path("v115.m4s"), run=_probe(out)), 0.8926, abs_tol=1e-4)


def test_an_fmp4_piece_is_read_through_its_header() -> None:
    """Голый ``.m4s`` ffprobe не читает («no tfhd was found»): голова прогона идёт впереди."""
    seen: list[list[str]] = []
    piece_overhang(Path("/r/v9.m4s"), Path("/r/init.mp4"), run=_probe("", seen))
    assert seen[0][-1] == "concat:/r/init.mp4|/r/v9.m4s"
    piece_overhang(Path("/r/v9.ts"), run=_probe("", seen))
    assert seen[1][-1] == "/r/v9.ts"


def test_picture_that_outlasts_the_sound_adds_nothing() -> None:
    """Конец в списке стоит по картинке: если звук кончился раньше, прибавлять нечего."""
    out = "video,20.0,0.04\naudio,19.0,0.02\n"
    assert piece_overhang(Path("v1.ts"), run=_probe(out)) == 0.0
    assert piece_overhang(Path("v1.ts"), run=_probe("video,20.0,0.04\n")) == 0.0


def test_a_packet_without_time_is_skipped_and_one_without_duration_still_counts() -> None:
    """``N/A`` ffprobe печатает словом: такой пакет конца не называет, но и не роняет меру."""
    out = "audio,N/A,0.04\naudio,12.5,N/A\nvideo,12.0,0.04\n"
    assert math.isclose(piece_overhang(Path("v1.ts"), run=_probe(out)), 0.46)


def test_an_unreadable_piece_or_one_without_picture_is_an_honest_unknown() -> None:
    """Ffprobe не поднялся, ничего не сказал или картинки нет - ``nan``, решает вызывающий."""

    def dead(*_a: object, **_k: object) -> None:
        raise subprocess.TimeoutExpired("ffprobe", 1.0)

    assert math.isnan(piece_overhang(Path("v1.ts"), run=dead))
    assert math.isnan(piece_overhang(Path("v1.ts"), run=_probe("")))
    assert math.isnan(piece_overhang(Path("v1.ts"), run=_probe("audio,9.0,0.02\n")))
