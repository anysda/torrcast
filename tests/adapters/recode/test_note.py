"""Отметка выложенного сегмента: край упаковки, калибровка профиля и счёт опозданий."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.adapters.recode.grids import grid, keys
from torrcast.adapters.recode.note import _note
from torrcast.adapters.recode.recoder_state import _State
from torrcast.adapters.recode.weights import Weights
from torrcast.domain.segment_container import FMP4
from torrcast.ports.journal.silent import Silent
from torrcast.ports.journal.slot import install

if TYPE_CHECKING:
    from pathlib import Path


class _Marks(Silent):
    """Лента, которая помнит отметки: молчание Silent для всего остального."""

    def __init__(self) -> None:
        self.rows: list[tuple[str, dict[str, object]]] = []

    def mark(self, name: str, **facts: object) -> None:
        self.rows.append((name, facts))


def _state(spare: Path, said: list[str]) -> _State:
    lines = grid()
    weights = Weights.of(keys(rate=2.0e6), lines)
    assert weights is not None
    return _State(
        source="src",
        audio=0,
        grid=lines,
        spare=spare / "recode",
        weights=weights,
        threshold=15.0,
        log=said.append,
    )


def test_the_edge_follows_the_last_published_piece_not_the_furthest(tmp_path: Path) -> None:
    """Перемотка назад начинает упаковку заново, и край обязан уехать назад вместе с ней.

    Считай край максимумом - и кодировщик решит, что всё позади уже выложено, и до конца
    показа не возьмётся ни за один кусок.
    """
    said: list[str] = []
    state = _state(tmp_path, said)

    _note(state, 9, "копия")
    _note(state, 2, "копия")

    assert state.edge == 2


def test_a_published_piece_stops_holding_the_publisher(tmp_path: Path) -> None:
    """Кусок ушёл наружу - выкладку он больше не держит, каким бы ни был исход."""
    said: list[str] = []
    state = _state(tmp_path, said)
    state.stuck[3], state.blocked = 1.0, 3

    _note(state, 3, "перекод")

    assert state.stuck == {} and state.blocked == -1


def test_only_a_copy_calibrates_the_profile(tmp_path: Path) -> None:
    """Копия - единственный честный замер «сколько на самом деле уезжает на ТВ»."""
    said: list[str] = []
    state = _state(tmp_path, said)
    state.spare.mkdir(parents=True)
    (tmp_path / "v0.ts").write_bytes(b"x" * int(12.0e6 * 10.0 / 8))

    _note(state, 0, "склейка")
    assert state.weights.measured == 0, "перекод профиль не калибрует: он мерит нас, не файл"

    _note(state, 0, "копия")
    assert state.weights.measured == 1 and state.weights.extra == 4.0


def test_a_heavy_piece_that_left_as_a_copy_is_counted_as_a_miss(tmp_path: Path) -> None:
    """Тяжёлый кусок, ушедший копией, - это будущий BUFFERING, и молчать о нём нельзя."""
    said: list[str] = []
    state = _state(tmp_path, said)
    state.played = 0.0

    _note(state, 1, "копия")

    assert state.late == 1
    assert any("ушёл копией" in line for line in said)


def test_pieces_behind_the_show_are_not_counted_as_misses(tmp_path: Path) -> None:
    """После перемотки прошлый прогон дописывает то, что уже никто не увидит."""
    said: list[str] = []
    state = _state(tmp_path, said)
    state.played = 200.0

    _note(state, 1, "копия")

    assert state.late == 0, "считать это опозданием - врать себе в отчёте"


def test_a_failed_merge_is_said_out_loud_even_without_the_trace(tmp_path: Path) -> None:
    """Отказ склейки - это вернувшийся разрыв на стыке, и он объясняет подвис."""
    said: list[str] = []
    state = _state(tmp_path, said)

    _note(state, 4, "перекод")

    assert any("склейка v4 не вышла" in line for line in said)
    assert state.late == 0, "перекод опозданием не считается"


def test_the_weight_that_went_out_is_read_from_the_name_the_container_gives(
    tmp_path: Path,
) -> None:
    """Единственный честный замер профиля - вес уехавшего файла, и файл надо найти.

    Промахнулись именем - и в ленте у каждого куска ноль мегабит, а поправка профиля
    не набирается никогда.
    """
    said: list[str] = []
    state = _state(tmp_path, said)
    state.container = FMP4
    marks = _Marks()
    install(marks)
    (tmp_path / "v5.m4s").write_bytes(b"x" * 2_000_000)

    _note(state, 5, "копия")

    assert marks.rows[-1][1]["мбит"] != 0.0, "вес уехавшего куска обязан найтись"
