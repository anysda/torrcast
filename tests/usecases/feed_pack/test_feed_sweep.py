"""Уборка по часам показа: сдать успевшее, погасить раздувшееся, вымести пройденное."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.usecases.feed_pack.world import feed, grid, lay, packer
from torrcast.usecases.feed_pack.feed_sweep import _prune, _sweep

if TYPE_CHECKING:
    from pathlib import Path


def test_the_publish_is_called_by_the_clock_even_when_nobody_asks_for_a_piece(
    tmp_path: Path,
) -> None:
    """Пока показ берёт куски с диска, к упаковке никто не идёт, а ffmpeg пишет в tmpfs.

    Замер: 897 МБ несданного за 14 минут показа, рост без предела и без единой строки.
    """
    show = feed(tmp_path)
    show.packer = packer(tmp_path, first=0, out=show.out)
    lay(show.packer.run, 0)
    lay(show.packer.run, 1)

    _sweep(show)

    assert (show.out / "v0.ts").exists() and show.packer.edge == 0


def test_a_halted_or_missing_run_is_left_alone(tmp_path: Path) -> None:
    """Погашенную упаковку часы не поднимают: она встала намеренно."""
    show = feed(tmp_path)
    _sweep(show)  # прогона нет - падать не на чем

    show.packer = packer(tmp_path, first=0, out=show.out, halted=True)
    lay(show.packer.run, 0)
    lay(show.packer.run, 1)

    _sweep(show)

    assert list(show.out.glob("v*.ts")) == []


def test_unclaimed_pieces_over_the_ceiling_put_the_run_out_with_one_honest_line(
    tmp_path: Path, journal: Path
) -> None:
    """Куски, которых никто не забирает, стоят памяти и не дают приёмнику ничего."""
    said: list[str] = []
    show = feed(tmp_path, log=said.append, pending_cap=1_000_000)
    show.packer = packer(tmp_path, first=0, out=show.out)
    lay(show.packer.run, 0, size=2_000_000)
    lay(show.packer.run, 1, size=2_000_000)
    lay(show.packer.run, 2, size=2_000_000)

    _sweep(show)

    assert show.packer.halted is True
    assert said == [
        "несданных кусков 2 МБ в памяти - упаковку гашу, подниму её по запросу приёмника"
    ]


def test_unclaimed_pieces_under_the_ceiling_never_stop_a_working_run(
    tmp_path: Path,
) -> None:
    """Порог отделяет поломку от плотной работы, а не спорит с ней."""
    said: list[str] = []
    show = feed(tmp_path, log=said.append, pending_cap=1_000_000)
    show.packer = packer(tmp_path, first=0, out=show.out)
    lay(show.packer.run, 0, size=900)
    lay(show.packer.run, 1, size=900)

    _sweep(show)

    assert show.packer.halted is False and said == []


def test_the_window_behind_the_show_is_the_free_seek_back(tmp_path: Path) -> None:
    """Позади показа держим окно ``keep``: глубже - уже перемотка, она перепакует поток."""
    show = feed(tmp_path, grid=grid(600.0, 10.0), keep=20.0)
    for slot in range(0, 12):
        lay(show.out, slot)

    _prune(show, played=100.0)

    assert sorted(int(p.stem[1:]) for p in show.out.glob("v*.ts")) == list(range(8, 12))


def test_the_leftovers_of_the_previous_place_of_the_show_are_swept_too(
    tmp_path: Path,
) -> None:
    """После отката назад впереди лежат места, до которых показ может уже и не дойти."""
    show = feed(tmp_path, grid=grid(600.0, 10.0), keep=600.0, ahead=2)
    show.packer = packer(tmp_path, first=0, edge=3, out=show.out)
    for slot in (0, 3, 5, 6, 40):
        lay(show.out, slot)

    _prune(show, played=5.0)

    assert sorted(int(p.stem[1:]) for p in show.out.glob("v*.ts")) == [0, 3, 5]


def test_without_a_run_nothing_ahead_is_touched(tmp_path: Path) -> None:
    """Прогона нет - край неизвестен, а гадать тут дороже, чем подождать."""
    show = feed(tmp_path, grid=grid(600.0, 10.0), keep=600.0)
    for slot in (0, 40):
        lay(show.out, slot)

    _prune(show, played=5.0)

    assert sorted(int(p.stem[1:]) for p in show.out.glob("v*.ts")) == [0, 40]
