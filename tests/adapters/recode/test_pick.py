"""Выбор захода: от края упаковки вперёд, подряд и ровно настолько, насколько успеваем."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.adapters.recode.grids import grid, keys
from torrcast.adapters.recode.pick import _pick
from torrcast.adapters.recode.recoder_state import _State
from torrcast.adapters.recode.weights import Weights

if TYPE_CHECKING:
    from pathlib import Path


def _state(spare: Path, rate: float = 2.0e6) -> _State:
    lines = grid()
    weights = Weights.of(keys(rate=rate), lines)
    assert weights is not None
    return _State(source="src", audio=0, grid=lines, spare=spare, weights=weights, threshold=15.0)


def test_the_run_starts_beyond_what_the_packer_has_already_published(tmp_path: Path) -> None:
    """Выложенный кусок перекодировать поздно: приёмник его либо забрал, либо заберёт."""
    state = _state(tmp_path)
    state.played, state.edge = 0.0, 3

    job = _pick(state)

    assert job is not None and job[0] == 4


def test_nothing_beyond_the_horizon_is_started(tmp_path: Path) -> None:
    """Горизонт - ограничение не по времени, а по tmpfs: готовые куски лежат в памяти.

    Дальше него заход не НАЧИНАЕТСЯ: работать впрок на полфильма вперёд значит забить
    память кусками, которые к своему часу уже вытеснят.
    """
    state = _state(tmp_path)
    state.played, state.edge, state.ahead = 0.0, 5, 10.0  # ближайший кусок - на 60-й секунде

    assert _pick(state) is None


def test_a_ready_or_given_up_piece_is_skipped(tmp_path: Path) -> None:
    """Готовый кусок и кусок, на котором сдались, заходу больше не нужны."""
    state = _state(tmp_path)
    state.played = 0.0
    state.done.add(0)
    (tmp_path / "v1.ts").write_bytes(b"x")

    job = _pick(state)

    assert job is not None and job[0] == 2


def test_the_head_of_the_run_goes_alone_and_therefore_fastest(tmp_path: Path) -> None:
    """Возьми голову в общий заход - срок считался бы по последнему куску, и она опоздала бы."""
    state = _state(tmp_path)
    state.played, state.head = 0.0, 0

    assert _pick(state) == (0, 0)


def test_a_run_never_stretches_past_its_own_cap(tmp_path: Path) -> None:
    """Заход длиннее отпущенного нельзя бросить на перемотке, поэтому он и ограничен."""
    state = _state(tmp_path)
    state.played = 0.0

    job = _pick(state)

    assert job is not None and job[1] - job[0] + 1 <= state.run_max


def test_a_lonely_heavy_piece_takes_a_light_neighbour_on_each_side(tmp_path: Path) -> None:
    """Остров перекода между двумя копиями роняет медиасессию обоими стыками сразу."""
    lines = grid()
    weights = Weights.of(keys(rate=0.5e6), lines)
    assert weights is not None
    raw = list(weights.raw)
    raw[5] = 20.0  # единственный тяжёлый кусок посреди лёгкого кино
    weights.raw = tuple(raw)
    state = _State(
        source="src", audio=0, grid=lines, spare=tmp_path, weights=weights, threshold=15.0
    )
    state.played, state.edge = 0.0, 0

    assert _pick(state) == (4, 6), "по лёгкому соседу с каждой стороны - один однородный заход"


def test_nothing_to_do_is_answered_by_none(tmp_path: Path) -> None:
    """Лёгкое кино: кодировщику браться не за что, и нитка уходит спать, а не крутится."""
    state = _state(tmp_path, rate=0.5e6)
    state.played = 0.0

    assert _pick(state) is None
