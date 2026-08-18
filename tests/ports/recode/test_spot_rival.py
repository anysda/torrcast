"""Зеркало договора, из которого собирается прогрев: те же слоты и то же решение."""

from __future__ import annotations

from pathlib import Path

from tests.usecases.playback.world import film_keys, grid
from torrcast.adapters.recode import Encode, Recoder, Weights
from torrcast.ports.recode.spot_rival import SpotRival

_ENCODE = Encode(preset="ultrafast", mbit=9.0)


class _Rival:
    """Кодировщик в объёме сборки прогрева и ни ручкой шире."""

    targets = (1, 4)
    encode = _ENCODE
    working = False


def _recoder(tmp_path: Path) -> Recoder:
    weights = Weights.of(film_keys(), grid())
    assert weights is not None
    return Recoder(
        source="http://ts/stream",
        audio=0,
        grid=grid(),
        spare=tmp_path / "recode",
        weights=weights,
        threshold=0.0,
        encode=_ENCODE,
    )


def test_the_real_recoder_answers_the_named_contract(tmp_path: Path) -> None:
    """Слоты и решение прогрев берёт у живого кодировщика, а не считает заново."""
    named: SpotRival = _recoder(tmp_path)

    assert isinstance(named.targets, tuple)
    assert named.encode.mbit == 9.0
    assert named.working is False


def test_the_assembly_asks_for_the_run_in_flight_too(tmp_path: Path) -> None:
    """Собранный прогрев обязан уметь замереть под этим же кодировщиком.

    Мера не косметическая: пока в этом договоре не было признака захода, показ отдавал
    прогреву кодировщика, соперником которого тот считаться не мог, - и сборка сходилась
    только потому, что каждый пакет называл кодировщика по-своему.
    """
    named: SpotRival = _Rival()

    assert named.targets == (1, 4)
    assert named.working is False
