"""Зеркало договора о кодировщике тяжёлых кусков: настоящий Recoder отвечает ему."""

from __future__ import annotations

from pathlib import Path

from tests.usecases.playback.world import film_keys, grid
from torrcast.adapters.recode.encode import Encode
from torrcast.adapters.recode.recoder import Recoder
from torrcast.adapters.recode.weights import Weights
from torrcast.ports.recode.spot_recoder import SpotRecoder


def _recoder(tmp_path: Path, threshold: float = 0.0) -> Recoder:
    weights = Weights.of(film_keys(), grid())
    assert weights is not None
    return Recoder(
        source="http://ts/stream",
        audio=0,
        grid=grid(),
        spare=tmp_path / "recode",
        weights=weights,
        threshold=threshold,
        encode=Encode(preset="ultrafast", mbit=9.0),
    )


def test_the_real_recoder_answers_the_named_contract(tmp_path: Path) -> None:
    """Показ спрашивает у кодировщика слоты, решение и место показа - и всё это у него есть."""
    named: SpotRecoder = _recoder(tmp_path)

    assert isinstance(named.targets, tuple)
    assert named.encode.mbit == 9.0
    assert named.played == 0.0


def test_the_show_moves_the_place_the_recoder_works_from(tmp_path: Path) -> None:
    """Место показа кодировщику ставит показ: от него кодировщик выбирает очередь."""
    named: SpotRecoder = _recoder(tmp_path)

    named.played = 120.0

    assert named.played == 120.0


def test_nothing_heavy_means_no_thread_at_all(tmp_path: Path) -> None:
    """Тяжёлых кусков нет - поток не поднимается вовсе, и это решение самого кодировщика."""
    named: SpotRecoder = _recoder(tmp_path, threshold=1000.0)

    assert named.targets == ()

    named.start()

    assert not (tmp_path / "recode").exists(), "без тяжёлых кусков каталог не заводится"
