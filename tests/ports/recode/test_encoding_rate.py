"""Зеркало доли решения, которую спрашивает лента: одно число, и договор на этом кончается."""

from __future__ import annotations

from dataclasses import dataclass

from torrcast.adapters.recode.encode import Encode
from torrcast.ports.recode.encoding_rate import EncodingRate


@dataclass(frozen=True)
class _Rate:
    """Решение в объёме ленты и ни ручкой шире."""

    mbit: float = 4.0


def test_the_real_encode_answers_the_narrow_share_too() -> None:
    """Настоящее решение подходит ленте целиком: доля отрезана от него, а не выдумана."""
    named: EncodingRate = Encode(preset="veryfast", mbit=9.0)

    assert named.mbit == 9.0


def test_the_share_asks_for_nothing_but_the_target_bitrate() -> None:
    """Мера ширины: лента не имеет права требовать больше одного числа.

    Отрасти договор хоть на ручку - и заглушка перестанет ему отвечать, а вместе с ней
    перестанут отвечать те, кто отдаёт ленте не полное решение, а только его цель.
    """
    named: EncodingRate = _Rate()

    assert named.mbit == 4.0
