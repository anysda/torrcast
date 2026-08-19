"""Зеркало завода точечного перекода: настоящий ``Encode`` отвечает договору."""

from __future__ import annotations

from torrcast.adapters.recode.encode import Encode
from torrcast.ports.recode.encoding import Encoding
from torrcast.usecases.playback.spot_encodings import SpotEncodings


def test_the_real_factory_answers_the_named_contract() -> None:
    """Показ заводит решение двумя настройками, и адаптер принимает ровно их."""
    named: SpotEncodings = Encode

    made: Encoding = named(preset="ultrafast", mbit=7.5)

    assert (made.preset, made.mbit) == ("ultrafast", 7.5)
    assert made.out_frame == 0, "кадр точечному перекоду не назначается - он тот же"
