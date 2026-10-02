"""Стенд сверок входа: кодировщик-свидетель и ответы сверок, общие для зеркал ``feed_clean``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from tests.usecases.feed_pack.world import factory, packer, tract
from torrcast.adapters.recode.encode import Encode

if TYPE_CHECKING:
    from pathlib import Path


class _Pace:
    def table(self) -> list[tuple[str, float]]:
        return [("ultrafast", 1.0), ("veryfast", 2.0)]


@dataclass
class Recoder:
    """Кодировщик тяжёлых кусков: помнит, чем его просили кодировать и гасили ли."""

    spare: Any = None
    done: set[int] = field(default_factory=set)
    fitted: list[tuple[float, str]] = field(default_factory=list)
    stopped: bool = False
    pace: _Pace = field(default_factory=_Pace)

    def fit(self, span: float, preset: str) -> Encode:
        self.fitted.append((span, preset))
        return Encode(preset=preset, mbit=7.5)

    def stop(self) -> None:
        self.stopped = True

    def opening(self, slot: int) -> None: ...

    def note(self, slot: int, how: str) -> None: ...

    def holding(self, slot: int, size: int = 0) -> bool:
        return False

    def after_recode(self, slot: int) -> bool:
        return False


def stand(
    clean: bool | tuple[bool | None, ...] | None, seen: list[str], piece: bool | None = True
) -> list[list[str]]:
    """Стенд захода: что ответили сверки входа и куска с полки, какие команды поднялись."""
    commands: list[list[str]] = []

    def _start(command: list[str], out: Path, run: Path, first: int, **kwargs: Any) -> Any:
        commands.append(command)
        run.mkdir(parents=True, exist_ok=True)
        return packer(out.parent, out=out, run=run, first=first)

    def _pilot(source: str, want: float) -> tuple[float, float]:
        seen.append("проба")
        return want, want

    answers = list(clean) if isinstance(clean, tuple) else [clean]

    def _clean(source: str, at: float) -> bool | None:
        seen.append(f"вход {at}")
        return answers.pop(0) if len(answers) > 1 else answers[0]

    def _piece(path: Path) -> bool | None:
        seen.append(f"кусок {path.name}")
        return piece

    tract(settle_start=_pilot, opens_clean=_clean, piece_opens=_piece, packer=factory(_start))
    return commands
