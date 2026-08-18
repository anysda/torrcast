"""Зеркало доли решения, которой различается прогретое: пресет, битрейт и метка."""

from __future__ import annotations

from dataclasses import dataclass

from torrcast.ports.recode.encoding_key import EncodingKey
from torrcast.recode import Encode


@dataclass(frozen=True)
class _Key:
    """Решение в объёме ключа прогретого и ни ручкой шире."""

    preset: str = "ultrafast"
    mbit: float = 9.0
    mark: str = ""


def test_the_real_encode_answers_the_key_share() -> None:
    """Метка ужатого кадра приходит из настоящего решения, а не собирается прогревом."""
    named: EncodingKey = Encode(preset="veryfast", mbit=9.0, frame=2160, ceiling=1080)

    assert named.preset == "veryfast"
    assert named.mbit == 9.0
    assert named.mark == ":1080p", "ужатый кадр обязан менять ключ прогретого"


def test_the_key_share_asks_for_nothing_but_what_changes_the_bytes() -> None:
    """Мера ширины: в ключ входит только то, от чего зависит содержимое куска."""
    named: EncodingKey = _Key()

    assert (named.preset, named.mbit, named.mark) == ("ultrafast", 9.0, "")
