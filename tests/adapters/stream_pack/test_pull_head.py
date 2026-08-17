"""Проверяет прогрев начала файла: это частный случай прогрева места со смещением ноль."""

from __future__ import annotations

from typing import Any

import pytest

from tests.conftest import module_of
from torrcast.adapters.stream_pack.pull_head import pull_head
from torrcast.domain.warm_open import HEAD_WARM

module = module_of("torrcast.adapters.stream_pack.pull_head")


def test_the_head_is_the_very_beginning_of_the_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """Без заголовка контейнера ffmpeg не откроет вход вовсе, и показ ждёт рой на пустом месте."""
    asked: list[tuple[str, int, int, Any]] = []

    def note(url: str, offset: int, upto: int = 0, alive: Any = None) -> int:
        asked.append((url, offset, upto, alive))
        return upto

    monkeypatch.setattr(module, "warm_at", note)
    assert pull_head("http://торрент/поток") == HEAD_WARM
    assert asked == [("http://торрент/поток", 0, HEAD_WARM, None)]


def test_the_size_and_the_liveness_are_passed_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Голову греют разной: у продолжения с середины она куском поменьше."""
    asked: list[tuple[int, int, Any]] = []

    def note(url: str, offset: int, upto: int = 0, alive: Any = None) -> int:
        asked.append((offset, upto, alive))
        return 0

    def alive() -> bool:
        return False

    monkeypatch.setattr(module, "warm_at", note)
    pull_head("http://торрент/поток", 1 << 20, alive)
    assert asked == [(0, 1 << 20, alive)], "признак жизни не доехал: отвергнутый релиз греется"
