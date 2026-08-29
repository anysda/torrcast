"""Выключенный прогрев оставляет улику в ленте показа."""

from __future__ import annotations

from pathlib import Path

from tests.usecases.playback.world import grid
from torrcast.domain.config import Config
from torrcast.ports.journal.silent import Silent
from torrcast.ports.journal.slot import install
from torrcast.usecases.playback._warmer import _warmer


class _Tape(Silent):
    """Лента, помнящая события общей двери писателя."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def emit(self, phase: str, event: str, **fields: object) -> None:
        self.events.append((phase, event))


def test_warming_switched_off_is_said_once_in_the_run_tape(tmp_path: Path) -> None:
    """Настройка видна в той же фазе ленты, по которой судят события ``warm-*``."""
    config = Config(warm=False, warm_dir=str(tmp_path / "warm"))
    tape = _Tape()
    install(tape)

    assert _warmer(config, "http://ts", 0, grid(), 0.0, "кино") is None
    assert tape.events == [("warm", "disabled")], (
        "выключенный прогрев не прочитан из ленты ровно один раз"
    )
