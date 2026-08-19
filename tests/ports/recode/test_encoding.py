"""Зеркало договора о кодировании: настоящий Encode обязан отвечать ему целиком."""

from __future__ import annotations

from torrcast.adapters.recode.encode import Encode
from torrcast.ports.recode.encoding import Encoding


def test_the_real_encode_answers_the_named_contract() -> None:
    """Показ зовёт решение о перекоде по своему договору, и адаптер отвечает на всё."""
    named: Encoding = Encode(preset="veryfast", mbit=9.0, frame=2160, ceiling=1080)

    assert named.preset == "veryfast"
    assert named.mbit == 9.0
    assert named.maxrate > named.mbit, "потолок кодера выше цели - на этом стоит сетка"
    assert named.out_frame == 1080
    assert named.hdr is False


def test_fitting_returns_the_same_contract_and_never_grows() -> None:
    """Ужатое под кусок решение - то же решение: показ считает по нему вес каждого куска."""
    named: Encoding = Encode(preset="veryfast", mbit=9.0)

    tight = named.fit(15.2, 16 * 1024 * 1024)

    assert isinstance(tight, Encode)
    assert tight.mbit <= named.mbit, "длинный кусок обязан ужимать цель, а не поднимать её"
