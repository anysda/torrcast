"""Подключение внешнего мира прогрева: слоты обязаны получить ровно то, что дали."""

from __future__ import annotations

from typing import Any

import torrcast.usecases.warm._state as _state
from tests.usecases.warm.world import FakeEnvironment
from torrcast.usecases.warm.configure import configure


def _own() -> FakeEnvironment:
    """Среда, у которой всё своё: по ней и видно, что слот взял именно её значение."""
    return FakeEnvironment(
        audio_mbit=0.5,
        max_segment_bytes=123,
        ts_overhead=1.5,
        names=lambda slot: f"кусок{slot}",
        slots=lambda name: -7,
        clock_face=lambda seconds: "часы",
        packer="упаковщик",
        pack=lambda *a, **k: "команда",
        pilot=lambda *a, **k: "пробный",
    )


def test_every_slot_takes_its_value_from_the_environment() -> None:
    """Один вызов - и весь внешний мир прогрева на месте, ни одного слота мимо."""
    environment: Any = _own()

    configure(environment)

    assert _state._environment is environment
    assert _state.segment_name(4) == "кусок4"
    assert _state.segment_slot("v4.ts") == -7
    assert _state._hms(0.0) == "часы"
    # Три слота медиатракта названы договорами порта, поэтому сверяются они не тождеством
    # ручки (среда отдаёт её связанной, каждый раз новой), а меткой ЭТОЙ среды в ответе.
    tract: Any = _state
    assert tract.Packer == "упаковщик"
    assert tract.ffmpeg_pack_command() == "команда"
    assert tract.pack_start("src", 1.0) == "пробный"
    assert (_state.AUDIO_MBIT, _state.MAX_SEGMENT_BYTES, _state.TS_OVERHEAD) == (0.5, 123, 1.5)


def test_a_second_call_replaces_the_world_and_does_not_mix_two() -> None:
    """Повторное подключение меняет мир целиком: половинчатая замена - это два мира разом."""
    first: Any = _own()
    second: Any = FakeEnvironment(
        audio_mbit=1.0,
        max_segment_bytes=7,
        ts_overhead=2.0,
        names=lambda slot: f"v{slot}",
        slots=lambda name: 1,
        clock_face=lambda seconds: "мгновение",
        packer="второй",
        pack=lambda *a, **k: "вторая",
        pilot=lambda *a, **k: "второй пробный",
    )

    configure(first)
    configure(second)

    assert _state._environment is second
    assert _state.segment_name(4) == "v4" and _state.MAX_SEGMENT_BYTES == 7
