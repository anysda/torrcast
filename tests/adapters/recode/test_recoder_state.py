"""Состояние кодировщика: цель куска, срок до выкладки и готовый кусок на диске."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.adapters.recode.grids import grid, keys
from torrcast.adapters.recode.recoder_state import _State
from torrcast.adapters.recode.weights import Weights
from torrcast.domain.segment_container import FMP4

if TYPE_CHECKING:
    from pathlib import Path


def _state(spare: Path, rate: float = 2.0e6) -> _State:
    lines = grid()
    weights = Weights.of(keys(rate=rate), lines)
    assert weights is not None
    return _State(source="src", audio=0, grid=lines, spare=spare, weights=weights, threshold=15.0)


def test_the_target_of_a_piece_is_counted_by_both_ceilings_of_this_receiver(tmp_path: Path) -> None:
    """Вес сегмента и битрейт приёмника - оба потолка, и оба этого показа, а не умолчания."""
    state = _state(tmp_path)

    encode = state.fit(span=20.0, preset="superfast")

    assert encode.preset == "superfast"
    assert encode.mbit < state.encode.mbit, "двадцатисекундный кусок просит меньше"
    assert encode.mbit <= state.threshold, "выше того, что тянет приёмник, не просим"


def test_a_run_in_flight_is_what_the_warmer_yields_to(tmp_path: Path) -> None:
    """Живой перекод под работающим прогревом теряет 30 % - поэтому прогрев и спрашивает."""
    state = _state(tmp_path)

    assert not state.working
    state.job = (0, 2, 0.0, 0.0, 1.0)
    assert state.working


def test_an_oversize_copy_is_judged_by_the_stat_when_there_is_one(tmp_path: Path) -> None:
    """Вес готовой копии известен точно одним ``stat``; без неё судим предсказанием по карте."""
    state = _state(tmp_path)
    state.cap = 16_000_000

    assert state.oversize(0, size=20_000_000), "точный вес выше потолка"
    assert not state.oversize(0, size=1_000), "точный вес ниже потолка"
    assert state.oversize(0) == (state.weights.size(0, state.grid.span(0)) > state.cap)


def test_a_ready_piece_is_found_by_its_own_name(tmp_path: Path) -> None:
    """Имя куска - это его место в фильме, и по нему же его ищет выкладка."""
    state = _state(tmp_path)

    assert state.ready(3) is None
    (tmp_path / "v3.ts").write_bytes(b"x")
    assert state.ready(3) == tmp_path / "v3.ts"


def test_the_deadline_is_counted_from_the_packer_not_from_the_show(tmp_path: Path) -> None:
    """Наружу сегмент выкладывает упаковщик, и опоздать надо к нему, а не к показу."""
    state = _state(tmp_path)
    state.played = 0.0

    far = state.slack(10)
    state.edge = 5  # упаковщик ушёл вперёд показа
    near = state.slack(10)

    assert near < far, "край упаковки съедает срок, а место показа о том не знает"


def test_a_stuck_slot_stops_blocking_once_it_is_released(tmp_path: Path) -> None:
    """Кусок ушёл наружу или перекод готов - выкладку он больше не держит."""
    state = _state(tmp_path)
    state.stuck[4] = 1.0
    state.blocked = 4

    state._unstick(4)

    assert state.stuck == {} and state.blocked == -1


def test_a_recoder_without_a_log_says_nothing_and_does_not_fall(tmp_path: Path) -> None:
    """Кодировщик работает впрок и ронять показ отсутствием журнала не имеет права."""
    said: list[str] = []
    state = _state(tmp_path)

    state._say("в пустоту")
    state.log = said.append
    state._say("в журнал")

    assert said == ["в журнал"]


def test_a_ready_piece_is_looked_for_under_the_name_the_receiver_container_gives(
    tmp_path: Path,
) -> None:
    """Готовый перекод ищется тем же именем, каким его кладёт заход, - иначе его нет.

    Разошлись имена - и выкладка не видит готового куска: место уходит в круг без
    прогресса, а зритель не получает картинки вовсе.
    """
    state = _state(tmp_path)
    state.container = FMP4
    (tmp_path / "v3.m4s").write_bytes(b"x")
    (tmp_path / "v4.ts").write_bytes(b"x")

    assert state.ready(3) == tmp_path / "v3.m4s"
    assert state.ready(4) is None, "кусок чужого контейнера готовым не считается"
