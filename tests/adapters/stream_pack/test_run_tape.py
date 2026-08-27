"""Лента прогона: на сколько счётчик каждой дорожки отстоит от времени фильма."""

from __future__ import annotations

import math
from pathlib import Path

from tests.usecases.feed_pack.world import packer
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.run_tape import run_tape
from torrcast.domain.segment_container import FMP4


def _piece(where: Path, name: str = "v0.m4s") -> Path:
    path = where / name
    path.write_bytes(b"x" * 32)
    return path


def test_the_tape_of_each_track_is_the_distance_of_its_counter_from_the_film(
    tmp_path: Path,
) -> None:
    """🔴 Живой замер: звук куска на 49.792, а картинка ТОГО ЖЕ куска - на 59.809.

    Лент выходит две: у дорожек не только свой счёт, но и свой ноль.
    """
    run = packer(tmp_path, container=FMP4, grid=Grid.uniform(60.0, 10.0))

    tape = run_tape(run, 1, _piece(run.run), None, lambda piece: (59.809, 49.792))

    assert tape == (49.809, 39.792)


def test_the_piece_is_asked_about_together_with_the_head_of_the_show(tmp_path: Path) -> None:
    """Голый фрагмент не открывается ничем - мерить ленту по нему было бы нечем."""
    asked: list[str] = []
    run = packer(tmp_path, container=FMP4, grid=Grid.uniform(60.0, 10.0))
    head = run.out / "init.mp4"
    head.write_bytes(b"h")
    piece = _piece(run.run)

    def starts(where: str | Path) -> tuple[float, float]:
        asked.append(str(where))
        return 1.0, 1.0

    run_tape(run, 0, piece, head, starts)

    assert asked == [f"concat:{head}|{piece}"]


def test_on_mpegts_the_tape_is_the_common_origin_and_nothing_is_asked(tmp_path: Path) -> None:
    """На mpegts метка куска - время фильма: оба захода пакуют одну ленту, поднятую origin."""
    asked: list[str] = []
    run = packer(tmp_path, grid=Grid(bounds=(0.0, 10.0), duration=20.0, origin=100.0))

    def starts(where: str | Path) -> tuple[float, float]:
        asked.append(str(where))
        return 0.0, 0.0

    tape = run_tape(run, 1, _piece(run.run, "v1.ts"), None, starts)

    assert tape == (100.0, 100.0) and asked == []


def test_a_track_that_did_not_answer_leaves_the_tape_unmeasured(tmp_path: Path) -> None:
    """Считать ленту по одной дорожке нельзя: у второй ноль свой и вывести его неоткуда."""
    run = packer(tmp_path, container=FMP4, grid=Grid.uniform(60.0, 10.0))

    assert run_tape(run, 0, _piece(run.run), None, lambda p: (math.nan, 49.792)) is None
    assert run_tape(run, 0, _piece(run.run), None, lambda p: (59.809, math.nan)) is None


def test_without_a_grid_there_is_nothing_to_measure_the_tape_against(tmp_path: Path) -> None:
    """Сетки у прогона нет (щупы и стенды) - и места куска на фильме нет тоже."""
    run = packer(tmp_path, container=FMP4)

    assert run_tape(run, 0, _piece(run.run), None, lambda p: (59.809, 49.792)) is None
