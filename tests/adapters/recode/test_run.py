"""Один заход кодировщика: приоритет процесса, пресет по сроку и цель по длине куска."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from tests.adapters.recode.grids import grid, keys
from tests.conftest import fake_packer
from torrcast.adapters.recode.presets import PRESETS
from torrcast.adapters.recode.recoder_state import _State
from torrcast.adapters.recode.run import HEAD_NICE, NICE, _run
from torrcast.adapters.recode.weights import Weights
from torrcast.usecases.feed_pack.packer import Packer

if TYPE_CHECKING:
    from pathlib import Path


def _state(spare: Path) -> _State:
    lines = grid()
    weights = Weights.of(keys(rate=2.0e6), lines)
    assert weights is not None
    state = _State(source="src", audio=0, grid=lines, spare=spare, weights=weights, threshold=15.0)
    state.stopped = True  # один круг: ждать настоящего ffmpeg тут нечего
    return state


def _commands(spare: Path, monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    seen: list[list[str]] = []

    def _remember(cls: object, command: list[str], /, *a: object, **k: object) -> Any:
        seen.append(command)
        return fake_packer(spare)

    monkeypatch.setattr(Packer, "start", classmethod(_remember))
    return seen


def test_the_head_of_the_run_is_not_niced_behind_the_packer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Голову ждёт старт показа, и каждая её секунда - секунда чёрного экрана.

    Замер («Моана 2», v0 длиной 19.96 с, ultrafast): под ``nice 15`` - 8.05 с, под
    ``nice 0`` - 5.84 с. Остальные заходы работают впрок и уступают процессор упаковке.
    """
    state = _state(tmp_path)
    seen = _commands(tmp_path, monkeypatch)
    state.head = 3

    _run(state, 3, 3)
    _run(state, 9, 11)

    assert seen[0][:3] == ["nice", "-n", str(HEAD_NICE)] == ["nice", "-n", "0"]
    assert seen[1][:3] == ["nice", "-n", str(NICE)] == ["nice", "-n", "15"]


def test_a_blocked_publisher_ends_the_bargaining_about_quality(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Пока мы выбираем пресет получше, приёмник ждёт наш кусок и никакого другого."""
    state = _state(tmp_path)
    seen = _commands(tmp_path, monkeypatch)
    state.played, state.edge = 0.0, -1

    _run(state, 20, 21)
    roomy = seen[-1][seen[-1].index("-preset") + 1]

    state.blocked = 20
    _run(state, 20, 21)
    urgent = seen[-1][seen[-1].index("-preset") + 1]

    # ``veryfast`` при умолчании плана (сосед уже работает) идёт медленнее реального
    # времени, поэтому на пути показа его не берут даже под щедрый срок.
    assert roomy == "superfast", "срок щедрый - берём качество"
    assert urgent == PRESETS[-1][0] == "ultrafast", "выкладка стоит - качество не торгуется"


def test_the_target_is_taken_from_the_longest_piece_of_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🔴 TC-483: заход идёт одним ``-b:v`` на все куски, значит судит самый длинный."""
    from torrcast.adapters.stream_pack.grid import Grid

    lines = Grid(bounds=(0.0, 6.0, 26.0, 32.0), duration=45.0, on_keys=True)
    weights = Weights.of(keys(rate=4.0e6), lines)
    assert weights is not None
    state = _State(
        source="src", audio=0, grid=lines, spare=tmp_path, weights=weights, threshold=10.0
    )
    state.stopped = True
    seen = _commands(tmp_path, monkeypatch)

    _run(state, 0, 2)
    long_run = float(seen[-1][seen[-1].index("-b:v") + 1].rstrip("M"))
    _run(state, 0, 0)
    short_run = float(seen[-1][seen[-1].index("-b:v") + 1].rstrip("M"))

    assert long_run == pytest.approx(state.fit(20.0, "veryfast").mbit, abs=0.01)
    assert long_run < short_run, "двадцатисекундный кусок обязан просить меньше шестисекундного"


def test_a_run_that_gave_nothing_is_not_tried_forever(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Заход не дал ни куска - помечаем их сделанными, чтобы не крутиться на месте вечно."""
    said: list[str] = []
    state = _state(tmp_path)
    state.log = said.append
    _commands(tmp_path, monkeypatch)

    _run(state, 4, 6)

    assert state.done == {4, 5, 6}
    assert state.made == 0 and state.pace.seen == 0, "помеха - это не замер скорости"
    assert any("не дало ни куска" in line for line in said)


def test_a_run_that_delivered_is_counted_by_its_own_packer_edge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Считаем по краю СВОЕГО упаковщика: готовый кусок из каталога уже мог забрать показ."""
    state = _state(tmp_path)
    said: list[str] = []
    state.log = said.append

    def _remember(cls: object, command: list[str], /, *a: object, **k: object) -> Any:
        return fake_packer(tmp_path, first=4, edge=5)

    monkeypatch.setattr(Packer, "start", classmethod(_remember))

    _run(state, 4, 6)

    assert state.done == {4, 5}, "выложено два куска из трёх - третий остаётся заходу"
    assert state.made == 2 and state.seconds > 0.0
    assert state.pace.seen == 1, "состоявшийся заход уточняет масштаб таблицы"
    assert any("перекодировал v4" in line for line in said)
