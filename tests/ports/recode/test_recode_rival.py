"""Зеркало соседа по процессору: прогрев спрашивает у живого перекода одно слово."""

from __future__ import annotations

from pathlib import Path

from tests.usecases.playback.world import film_keys, grid
from torrcast.adapters.recode import Encode, Recoder, Weights
from torrcast.ports.recode.recode_rival import RecodeRival


class _Rival:
    """Кодировщик в объёме, в каком его знает прогрев, и ни ручкой шире."""

    def __init__(self, working: bool = False) -> None:
        self.working = working


def test_the_real_recoder_answers_the_named_contract(tmp_path: Path) -> None:
    """Настоящий кодировщик умеет сказать, идёт ли у него заход прямо сейчас."""
    weights = Weights.of(film_keys(), grid())
    assert weights is not None
    named: RecodeRival = Recoder(
        source="http://ts/stream",
        audio=0,
        grid=grid(),
        spare=tmp_path / "recode",
        weights=weights,
        threshold=0.0,
        encode=Encode(preset="ultrafast", mbit=9.0),
    )

    assert named.working is False, "заход не начинался - соперника у прогрева ещё нет"


def test_the_rival_asks_for_nothing_but_the_run_in_flight() -> None:
    """Мера ширины: замереть прогрев обязан по одному признаку, а не по знанию о чужой работе."""
    named: RecodeRival = _Rival(working=True)

    assert named.working is True
