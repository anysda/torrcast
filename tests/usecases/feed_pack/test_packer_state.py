"""Поля прогона упаковки: с чего он начинается и какие пороги у него по умолчанию."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.usecases.feed_pack.world import packer
from torrcast.domain.profile import CAUTIOUS

if TYPE_CHECKING:
    from pathlib import Path


def test_a_fresh_run_stands_right_before_its_own_first_segment(tmp_path: Path) -> None:
    """Прогон, не выложивший ничего, стоит ровно перед своим первым куском.

    Без этого «край» и «ниже края» бессмысленны до первого publish, и запрос первого
    же куска выглядел бы для показа перемоткой назад.
    """
    assert packer(tmp_path, first=7).edge == 6
    assert packer(tmp_path).edge == -1


def test_a_run_that_already_published_never_slides_its_edge_back(tmp_path: Path) -> None:
    """Заданный край не опускается до ``first - 1``: выложенное не развыкладывается."""
    assert packer(tmp_path, first=3, edge=9).edge == 9


def test_the_defaults_are_the_cautious_receiver_and_no_limits(tmp_path: Path) -> None:
    """Умолчания осторожные: предела захода нет, потолок куска - профиль приёмника."""
    run = packer(tmp_path)

    assert run.first == 0 and run.last == -1
    assert run.cap == CAUTIOUS.max_segment_bytes
    assert (run.began, run.at, run.rate, run.burst) == (0.0, 0.0, 0.0, 0.0)


def test_a_fresh_run_is_alive_unblamed_and_uncounted(tmp_path: Path) -> None:
    """Свежий прогон никем не снят, ни в чём не обвинён и ещё не сосчитан.

    Признаки разные по смыслу: ``halted`` - пауза на пульте, ``stopped`` - мы сами,
    ``blamed`` - обрыв уже посчитан, ``whole`` - ответ «дочитал» ещё не считали.
    """
    run = packer(tmp_path)

    assert run.halted is False and run.stopped == ""
    assert run.blamed is False and run.whole is None
    assert run.grid is None and run.spare is None
    assert run.told is None and run.hold is None and run.shrink is None
