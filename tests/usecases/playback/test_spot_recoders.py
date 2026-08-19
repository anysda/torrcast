"""Зеркало завода кодировщика: корень кладёт показу настоящий класс адаптера."""

from __future__ import annotations

from pathlib import Path

from tests.usecases.playback.world import film_keys, grid
from torrcast.adapters.recode.encode import Encode
from torrcast.adapters.recode.recoder import Recoder
from torrcast.adapters.recode.weights import Weights
from torrcast.ports.recode.spot_recoder import SpotRecoder
from torrcast.usecases.playback.spot_recoders import SpotRecoders


def test_the_real_factory_answers_the_named_contract(tmp_path: Path) -> None:
    """Завод зовут теми же именами доводов, что и на боевом пути, и он отдаёт кодировщик."""
    named: SpotRecoders = Recoder
    weights = Weights.of(film_keys(), grid())
    assert weights is not None

    made: SpotRecoder = named(
        source="http://ts/stream",
        audio=0,
        grid=grid(),
        spare=tmp_path / "recode",
        weights=weights,
        threshold=0.0,
        cap=16 * 1024 * 1024,
        encode=Encode(preset="ultrafast", mbit=9.0),
    )

    assert made.encode.preset == "ultrafast"
