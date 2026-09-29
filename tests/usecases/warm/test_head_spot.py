"""Тяжёлый стартовый кусок прогрев перекодирует первым и ровно один раз."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.usecases.warm.world import warmer
from torrcast.usecases.warm.head_spot import _head_spot

if TYPE_CHECKING:
    from pathlib import Path


def test_a_heavy_start_is_taken_first(tmp_path: Path) -> None:
    """Место начала показа тяжелее потолка - оно и есть первая работа."""
    assert (
        _head_spot(warmer(tmp_path, began_at=3, spots=(3,), spot_encode=object(), ahead=True)) == 3
    )


def test_a_recoded_start_is_not_taken_again(tmp_path: Path) -> None:
    """После первого захода стоит метка, и кусок больше не берётся."""
    warm = warmer(tmp_path, spots=(0,), spot_encode=object(), ahead=True)
    warm.vault.spot(0).touch()

    assert _head_spot(warm) is None


def test_nothing_to_do_without_a_heavy_start(tmp_path: Path) -> None:
    """Лёгкий старт, нет перекода или место не даётся - обычный порядок прогрева."""
    assert _head_spot(warmer(tmp_path, spots=(2,), spot_encode=object(), ahead=True)) is None
    assert _head_spot(warmer(tmp_path, spots=(0,), ahead=True)) is None
    warm = warmer(tmp_path, spots=(0,), spot_encode=object(), ahead=True)
    warm.hopeless.add(0)
    assert _head_spot(warm) is None


def test_the_current_episode_does_not_recode_what_the_show_already_gave(tmp_path: Path) -> None:
    """У текущей серии стартовый кусок отдал живой показ - прогреву он первым не нужен."""
    warm = warmer(tmp_path, began_at=3, spots=(3,), spot_encode=object())

    assert _head_spot(warm) is None, "прогрев текущей серии перекодирует уже отданный старт"
