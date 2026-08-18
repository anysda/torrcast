"""Зеркало сборки прогрева: одно решение о кодировании у показа и у прогрева."""

from __future__ import annotations

from pathlib import Path

import pytest

import torrcast.usecases.playback._show_state as _state
from tests.usecases.playback.world import film_keys, grid
from torrcast.domain.config import Config
from torrcast.ports.journal import Silent, install
from torrcast.recode import Encode, Recoder, Weights, whole_encode
from torrcast.usecases.playback._warmer import _warmer


@pytest.fixture(autouse=True)
def _tract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_state, "film_keys", lambda source: film_keys())
    monkeypatch.setattr(_state, "weights_of", Weights.of)
    monkeypatch.setattr(_state, "Recoder", Recoder)
    monkeypatch.setattr(_state, "Encode", Encode)
    monkeypatch.setattr(_state, "whole_encode", whole_encode)


def test_warming_switched_off_means_no_warmer_at_all(tmp_path: Path) -> None:
    """Прогрев выключен настройкой - собирать нечего."""
    config = Config(warm=False, warm_dir=str(tmp_path / "warm"))

    assert _warmer(config, "http://ts", 0, grid(), 0.0, "кино") is None


def test_the_whole_recode_leaves_no_spots_to_the_warmer(tmp_path: Path) -> None:
    """Файл едет сплошным перекодом - точечных слотов у прогрева нет и быть не может."""
    config = Config(warm=True, warm_dir=str(tmp_path / "warm"))
    whole = whole_encode(9.0)

    made = _warmer(config, "http://ts", 0, grid(), 0.0, "кино", whole=whole)

    assert made is not None
    assert made.encode is whole
    assert made.spots == (), "поверх сплошного перекода перекодировать нечего"


def test_the_spots_of_the_show_become_the_spots_of_the_warm_up(tmp_path: Path) -> None:
    """Тяжёлые куски греются ТЕМИ ЖЕ слотами и тем же решением, что берёт живой показ."""
    config = Config(warm=True, warm_dir=str(tmp_path / "warm"))
    weights = Weights.of(film_keys(), grid())
    assert weights is not None
    recoder = Recoder(
        source="http://ts",
        audio=0,
        grid=grid(),
        spare=tmp_path / "recode",
        weights=weights,
        threshold=0.0,
        encode=Encode(preset="ultrafast", mbit=9.0),
    )

    made = _warmer(config, "http://ts", 0, grid(), 0.0, "кино", recoder=recoder)

    assert made is not None
    assert made.encode is None, "прогрев ушёл в сплошной перекод там, где показ отдаёт копию"
    assert made.spots == recoder.targets
    assert made.spot_encode is recoder.encode


def test_the_place_of_the_show_becomes_the_place_of_the_warm_up(tmp_path: Path) -> None:
    """Греют с того места, откуда смотрят: голова фильма - потом."""
    config = Config(warm=True, warm_dir=str(tmp_path / "warm"))

    made = _warmer(config, "http://ts", 0, grid(), 95.0, "кино")

    assert made is not None
    assert made.began_at == grid().slot_at(95.0)


class _Noted(Silent):
    """Молчащая лента, которая помнит одну запись плана кодирования."""

    def __init__(self) -> None:
        self.plans: list[tuple[str, float]] = []

    def plan(self, pack: str, warm: str, spots: int, preset: str = "", mbit: float = 0.0) -> None:
        self.plans.append((preset, mbit))


def test_the_plan_names_the_decision_the_spots_are_taken_with(tmp_path: Path) -> None:
    """Точечный перекод есть - в записи плана стоят ЕГО пресет и битрейт, а не чужие."""
    config = Config(warm=True, warm_dir=str(tmp_path / "warm"))
    weights = Weights.of(film_keys(), grid())
    assert weights is not None
    recoder = Recoder(
        source="http://ts",
        audio=0,
        grid=grid(),
        spare=tmp_path / "recode",
        weights=weights,
        threshold=0.0,
        encode=Encode(preset="ultrafast", mbit=9.0),
    )
    noted = _Noted()
    install(noted)
    try:
        _warmer(config, "http://ts", 0, grid(), 0.0, "кино", recoder=recoder)
    finally:
        install(Silent())

    assert noted.plans == [("ultrafast", 9.0)]


def test_without_any_recode_the_plan_stays_empty(tmp_path: Path) -> None:
    """Ни сплошного, ни точечного перекода - в записи пустой пресет и нулевой битрейт."""
    config = Config(warm=True, warm_dir=str(tmp_path / "warm"))
    noted = _Noted()
    install(noted)
    try:
        _warmer(config, "http://ts", 0, grid(), 0.0, "кино")
    finally:
        install(Silent())

    assert noted.plans == [("", 0.0)]
