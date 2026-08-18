"""Три замера прогона: когда достанет место фильма, сколько держит и докуда дошёл каталог."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.usecases.feed_pack.world import hand, lay, packer
from torrcast.adapters.stream_pack.packer_measure import _eta, _frontier, _pending

if TYPE_CHECKING:
    from pathlib import Path


def test_a_run_without_a_pace_never_makes_anyone_wait(tmp_path: Path) -> None:
    """``rate <= 0`` - ffmpeg читает во весь опор: ждать нечего, ноль."""
    run = packer(tmp_path, rate=0.0, began=0.0, at=0.0, burst=0.0, now=hand(100.0).monotonic)

    assert _eta(run, 3600.0) == 0.0


def test_the_wait_is_counted_from_the_pace_of_ffmpeg_and_not_from_our_guess(tmp_path: Path) -> None:
    """Планка чтения - ``-ss + burst + прошло * rate``; выше неё ждать в темпе ``rate``."""
    run = packer(tmp_path, rate=1.0, burst=60.0, at=100.0, began=100.0, now=hand(110.0).monotonic)

    # Планка: 100 + 60 + 10 * 1 = 170 с фильма.
    assert _eta(run, 200.0) == 30.0
    assert _eta(run, 170.0) == 0.0
    assert _eta(run, 100.0) == 0.0, "ниже планки ждать нечего, а не отрицательно"


def test_the_wait_shrinks_twice_on_a_double_pace(tmp_path: Path) -> None:
    """Темп вдвое выше - и планка выше, и остаток дочитывается вдвое быстрее."""
    run = packer(tmp_path, rate=2.0, burst=0.0, at=0.0, began=100.0, now=hand(110.0).monotonic)

    # Планка: 0 + 0 + 10 * 2 = 20 с фильма; до 40-й секунды ещё 20 с фильма в темпе 2.
    assert _eta(run, 40.0) == 10.0


def test_the_unclaimed_bytes_are_counted_over_the_whole_run_directory(tmp_path: Path) -> None:
    """Несданное - это ВЕСЬ каталог прогона, включая склейку и пишущийся прямо сейчас кусок."""
    run = packer(tmp_path)
    lay(run.run, 0, size=1000)
    lay(run.run, 1, size=500)
    (run.run / "mix0.ts").write_bytes(b"x" * 300)
    lay(run.out, 5, size=9999)

    assert _pending(run) == 1800, "выложенное наружу в несданное попадать не имеет права"


def test_a_missing_run_directory_weighs_nothing_instead_of_raising(tmp_path: Path) -> None:
    """Каталога прогона нет - это ноль байт, а не исключение на горячем пути."""
    run = packer(tmp_path)
    (run.run / "..").resolve()
    run.run.rmdir()

    assert _pending(run) == 0


def test_the_frontier_counts_the_whole_directory_and_ignores_the_foreign_past(
    tmp_path: Path,
) -> None:
    """Глоб каталога считает всё от ``first`` и выше; ниже - чужие куски прошлых прогонов."""
    run = packer(tmp_path, first=3)
    for slot in (1, 3, 4):
        lay(run.out, slot)

    assert _frontier(run) == 4


def test_an_empty_window_answers_the_place_right_before_the_first(tmp_path: Path) -> None:
    """Готового нет - ответ ``first - 1``, то есть «прогон стоит перед своим первым»."""
    assert _frontier(packer(tmp_path, first=3)) == 2
