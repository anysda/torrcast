"""Поля прогрева и справки по ним: что считается запасом и когда прогрев обязан уступить."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from tests.usecases.warm.world import grid, lay, vault
from torrcast.usecases.warm.settings import GUARD_LOW, WARM_NICE, WARM_RATE
from torrcast.usecases.warm.warmer_state import _State

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class _Rival:
    working: bool = False


def _state(root: Path, key: str = "k", **kwargs: object) -> _State:
    store = vault(root, key=key)
    return _State(source="src", audio=0, grid=grid(), vault=store, **kwargs)  # type: ignore[arg-type]


def test_the_defaults_are_the_polite_ones(tmp_path: Path) -> None:
    """Умолчания прогрева - вежливые: тот же темп и тот же ``nice``, что названы порогами."""
    state = _state(tmp_path)

    assert (state.rate, state.nice) == (WARM_RATE, WARM_NICE)
    assert state.began_at == 0 and state.misgrid == -1 and state.after is None
    assert state.skews == {} and not state.stopped and not state.idle


def test_the_reserve_counts_only_what_the_show_would_take(tmp_path: Path) -> None:
    """Копия тяжелее потолка приёмника наружу не идёт и запасом не является."""
    state = _state(tmp_path, cap=500)
    lay(state.vault, 0, size=100)
    lay(state.vault, 1, size=1000)

    assert state.warmed == state.grid.span(0), "тяжёлая копия зачлась запасом"
    assert not state.done, "неполный фильм назвался готовым"


def test_a_heavy_place_without_a_recode_is_not_done_yet(tmp_path: Path) -> None:
    """Пока на месте тяжёлого куска лежит копия, «готово» - ложь."""
    state = _state(tmp_path, spots=(1,), spot_encode=object())
    for slot in range(state.grid.count):
        lay(state.vault, slot)

    assert state._spots_left() == (1,), "тяжёлое место числится сделанным"
    assert not state.done

    state.vault.spot(1).touch()
    assert state._spots_left() == () and state.done, "перекод лёг, а прогрев всё не готов"


def test_without_a_spot_encode_there_is_nothing_to_bring_to_a_recode(tmp_path: Path) -> None:
    """Перекодировать нечем - и точечных работ у прогрева нет вовсе."""
    state = _state(tmp_path, spots=(1,))
    for slot in range(state.grid.count):
        lay(state.vault, slot)

    assert state._spots_left() == () and state.done


def test_the_warming_yields_to_a_thin_reserve_and_to_the_live_recoder(tmp_path: Path) -> None:
    """Две причины замереть, и обе про то, что показ важнее работы впрок."""
    state = _state(tmp_path)

    state.slack = GUARD_LOW - 1.0
    assert state._must_yield(), "просевший запас не заморозил прогрев"

    state.slack = GUARD_LOW + 1.0
    assert not state._must_yield()

    state.rival = _Rival(working=True)
    assert state._busy_rival() and state._must_yield(), "чужой заход не заморозил прогрев"

    state.rival.working = False
    assert not state._busy_rival() and not state._must_yield()


def test_an_unmeasured_reserve_never_freezes_the_warming(tmp_path: Path) -> None:
    """Запас не мерили вовсе (mock, приёмник молчит) - гадать за показ нельзя."""
    state = _state(tmp_path)
    state.slack = 0.0

    assert not state._must_yield()


def test_the_reserve_and_the_stop_reach_the_whole_chain(tmp_path: Path) -> None:
    """Число одно на всю цепочку: обе серии тянут ту же раздачу и жгут тот же процессор."""
    state = _state(tmp_path)
    state.after = _state(tmp_path, key="следующая")

    state.feed(12.0)
    assert (state.slack, state.after.slack) == (12.0, 12.0), "запас не дошёл до соседа"

    state.stop()
    assert state.stopped and state.after.stopped, "снятие показа не дошло до соседа"


def test_the_thread_of_the_warming_belongs_to_the_subclass(tmp_path: Path) -> None:
    """Тело нитки живёт в :class:`Warmer`: голая база поднимать её не умеет и не врёт."""
    import pytest

    state = _state(tmp_path)
    with pytest.raises(NotImplementedError):
        state._work()


def test_the_log_is_silent_until_someone_hands_it_over(tmp_path: Path) -> None:
    """Без журнала прогрев молчит, а не падает: строка - не обязательная часть работы."""
    said: list[str] = []
    state = _state(tmp_path)

    state._say("в никуда")
    state.log = said.append
    state._say("в журнал")

    assert said == ["в журнал"]
