"""Зеркало :mod:`torrcast.usecases.warm._warm_count`: что из прогретого идёт в счёт."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.usecases.warm.world import grid, lay, vault
from torrcast.adapters.recode import Encode
from torrcast.usecases.warm._warm_count import _all_warmed, _spots_left, _warmed

if TYPE_CHECKING:
    from pathlib import Path

    from torrcast.usecases.warm.vault import Vault


def _full(store: Vault, count: int) -> None:
    """Положить весь фильм копией: столько кусков, сколько мест в сетке."""
    for slot in range(count):
        lay(store, slot)


def test_the_reserve_counts_only_what_the_show_would_take(tmp_path: Path) -> None:
    """Копия тяжелее потолка приёмника наружу не идёт и запасом не является."""
    lines, store = grid(), vault(tmp_path)
    lay(store, 0, size=100)
    lay(store, 1, size=1000)

    assert _warmed(lines, store, cap=500) == lines.span(0), "тяжёлая копия зачлась запасом"
    assert not _all_warmed(lines, store, 500, (), None), "неполный фильм назвался готовым"


def test_a_heavy_place_without_a_recode_is_not_done_yet(tmp_path: Path) -> None:
    """Пока на месте тяжёлого куска лежит копия, «готово» - ложь."""
    lines, store = grid(), vault(tmp_path)
    mark = Encode(preset="ultrafast", mbit=1.0)
    _full(store, lines.count)

    assert _spots_left(store, (1,), mark) == (1,), "тяжёлое место числится сделанным"
    assert not _all_warmed(lines, store, 0, (1,), mark)

    store.spot(1).touch()
    assert _spots_left(store, (1,), mark) == () and _all_warmed(lines, store, 0, (1,), mark), (
        "перекод лёг, а прогрев всё не готов"
    )


def test_without_a_spot_encode_there_is_nothing_to_bring_to_a_recode(tmp_path: Path) -> None:
    """Перекодировать нечем - и точечных работ у прогрева нет вовсе."""
    lines, store = grid(), vault(tmp_path)
    _full(store, lines.count)

    assert _spots_left(store, (1,), None) == () and _all_warmed(lines, store, 0, (1,), None)
