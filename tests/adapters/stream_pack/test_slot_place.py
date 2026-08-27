"""Где на ленте картинки и на ленте звука стоит место этого слота."""

from __future__ import annotations

import math
from pathlib import Path

from tests.usecases.feed_pack.world import packer
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.slot_place import slot_place


def test_the_place_of_the_slot_is_told_for_each_tape_of_the_run(tmp_path: Path) -> None:
    """🔴 Лент две: на CMAF счётчик у каждой дорожки свой, и между ними живые 10.0 с."""
    run = packer(tmp_path, grid=Grid.uniform(60.0, 10.0))
    run.tape = (-6134.545, -6144.649)

    assert slot_place(run, 2) == (20.0 - 6134.545, 20.0 - 6144.649)


def test_on_mpegts_the_place_stays_the_grid_lifted_by_the_common_origin(tmp_path: Path) -> None:
    """Прежнее ``grid.start(slot) + grid.origin`` знак в знак: там метка - время фильма."""
    run = packer(tmp_path, grid=Grid(bounds=(0.0, 10.0, 20.0), duration=30.0, origin=100.0))
    run.tape = (100.0, 100.0)

    assert slot_place(run, 2) == (120.0, 120.0)


def test_a_run_without_a_grid_has_no_place_to_check_against(tmp_path: Path) -> None:
    """Сетки нет (щупы и стенды) - сверять не с чем, и место не проверяется вовсе."""
    run = packer(tmp_path)
    run.tape = (0.0, 0.0)
    picture, sound = slot_place(run, 1)

    assert math.isnan(picture) and math.isnan(sound)


def test_a_tape_not_yet_measured_checks_no_place_either(tmp_path: Path) -> None:
    """Лента ещё не измерена - сверять место с невычисленной лентой нельзя."""
    run = packer(tmp_path, grid=Grid.uniform(60.0, 10.0))
    picture, sound = slot_place(run, 1)

    assert math.isnan(picture) and math.isnan(sound)
