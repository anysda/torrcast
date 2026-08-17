"""Подключение внешнего мира прогрева: слоты обязаны получить ровно то, что дали."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import torrcast.usecases.warm._state as _state
from tests.usecases.warm.world import FakeEnvironment
from torrcast.usecases.warm.configure import configure

if TYPE_CHECKING:
    import pytest


class _Environment(FakeEnvironment):
    """Среда, у которой всё своё: по ней и видно, что слот взял именно её значение."""

    audio_mbit = 0.5
    max_segment_bytes = 123
    ts_overhead = 1.5

    @staticmethod
    def segment_name(slot: int) -> str:
        return f"кусок{slot}"

    @staticmethod
    def segment_slot(name: str) -> int:
        return -7

    @staticmethod
    def hms(seconds: float) -> str:
        return "часы"

    @property
    def packer_type(self) -> object:
        return "упаковщик"

    @staticmethod
    def pack_command(*args: object, **kwargs: object) -> object:
        return "команда"

    @staticmethod
    def pack_start(*args: object, **kwargs: object) -> object:
        return "пробный"


def _restore(monkeypatch: pytest.MonkeyPatch) -> None:
    """Вернуть боевые слоты после теста: они общие на весь прогон."""
    for name in (
        "segment_name",
        "segment_slot",
        "_hms",
        "Packer",
        "ffmpeg_pack_command",
        "pack_start",
        "AUDIO_MBIT",
        "MAX_SEGMENT_BYTES",
        "TS_OVERHEAD",
        "_environment",
    ):
        monkeypatch.setattr(_state, name, getattr(_state, name), raising=False)


def test_every_slot_takes_its_value_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Один вызов - и весь внешний мир прогрева на месте, ни одного слота мимо."""
    _restore(monkeypatch)
    environment: Any = _Environment()

    configure(environment)

    assert _state._environment is environment
    assert _state.segment_name(4) == "кусок4"
    assert _state.segment_slot("v4.ts") == -7
    assert _state._hms(0.0) == "часы"
    assert _state.Packer == "упаковщик"
    assert _state.ffmpeg_pack_command() == "команда"
    assert _state.pack_start() == "пробный"
    assert (_state.AUDIO_MBIT, _state.MAX_SEGMENT_BYTES, _state.TS_OVERHEAD) == (0.5, 123, 1.5)


def test_a_second_call_replaces_the_world_and_does_not_mix_two(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Повторное подключение меняет мир целиком: половинчатая замена - это два мира разом."""
    _restore(monkeypatch)
    first: Any = _Environment()
    second: Any = FakeEnvironment()
    second.audio_mbit, second.max_segment_bytes, second.ts_overhead = 1.0, 7, 2.0
    second.segment_name = lambda slot: f"v{slot}"
    second.segment_slot = lambda name: 1
    second.hms = lambda seconds: "мгновение"
    second.packer_type = "второй"
    second.pack_command = lambda *a, **k: "вторая"
    second.pack_start = lambda *a, **k: "второй пробный"

    configure(first)
    configure(second)

    assert _state._environment is second
    assert _state.segment_name(4) == "v4" and _state.MAX_SEGMENT_BYTES == 7
