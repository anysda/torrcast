"""Стенд ленты показа: ручные часы, поддельный процесс и мелкий инвентарь.

Часы тут ручные, сна нет вовсе, ffmpeg не поднимается: зеркала обязаны мерить решение
показа, а не терпеливость машины.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import torrcast.usecases.feed_pack._state as _state
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.usecases.feed_pack.feed import Feed
from torrcast.usecases.feed_pack.packer import Packer

if TYPE_CHECKING:
    import pytest


@dataclass
class FakeClock:
    """Монотонные часы под рукой зеркала: сон не спит, а двигает стрелку."""

    now: float = 1000.0
    slept: list[float] = field(default_factory=list)
    naps: int = 1000

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds
        if len(self.slept) > self.naps:
            raise AssertionError(
                f"показ уснул {len(self.slept)} раз подряд: ожидание не кончается. "
                "Самое долгое честное ожидание тут - `wait` по 0.2 с, то есть сотни "
                "снов, так что тысяча - это уже вечный цикл."
            )


@dataclass
class FakeProc:
    """Процесс упаковки, которым распоряжается зеркало, а не операционная система."""

    code: int | None = None
    signals: list[str] = field(default_factory=list)

    def poll(self) -> int | None:
        return self.code

    def wait(self, timeout: float | None = None) -> int:
        self.code = 0 if self.code is None else self.code
        return self.code

    def terminate(self) -> None:
        self.signals.append("terminate")
        if self.code is None:
            self.code = -15

    def kill(self) -> None:
        self.signals.append("kill")
        self.code = -9


@dataclass
class FakeVault:
    """Хранилище прогретого: каталог на диске под именами той же сетки."""

    dir: Path

    def path(self, slot: int) -> Path:
        return self.dir / f"v{slot}.ts"


def clock(monkeypatch: pytest.MonkeyPatch, now: float = 1000.0) -> FakeClock:
    """Подставить показу ручные часы на время одного теста."""
    fake = FakeClock(now=now)
    monkeypatch.setattr(_state, "clock_port", fake)
    return fake


def grid(duration: float = 60.0, step: float = 10.0) -> Grid:
    """Ровная сетка: шесть кусков по десять секунд."""
    return Grid.uniform(duration, step)


def packer(root: Path, **kwargs: Any) -> Packer:
    """Прогон упаковки поверх свежих каталогов, без единого ffmpeg."""
    out = kwargs.pop("out", None) or root / "out"
    run = kwargs.pop("run", None) or out / "pack"
    out.mkdir(parents=True, exist_ok=True)
    run.mkdir(parents=True, exist_ok=True)
    proc = kwargs.pop("proc", None) or FakeProc()
    return Packer(proc=proc, out=out, run=run, **kwargs)


def feed(root: Path, **kwargs: Any) -> Feed:
    """Лента показа на ровной сетке поверх свежего каталога показа."""
    out = kwargs.pop("out", None) or root / "out"
    out.mkdir(parents=True, exist_ok=True)
    lines = kwargs.pop("grid", None) or grid()
    kwargs.setdefault("wait", 0.0)
    return Feed(source="src", audio=0, out=out, grid=lines, **kwargs)


def signals(run: Packer) -> list[str]:
    """Какие сигналы получил процесс прогона: на стенде он поддельный и это знает стенд."""
    return cast(FakeProc, run.proc).signals


def vault(root: Path) -> FakeVault:
    """Каталог прогретого на диске."""
    where = root / "warm"
    where.mkdir(parents=True, exist_ok=True)
    return FakeVault(dir=where)


def lay(where: Path, slot: int, size: int = 1024) -> Path:
    """Положить в каталог кусок нужного веса под именем сетки."""
    path = where / f"v{slot}.ts"
    path.write_bytes(b"x" * size)
    return path
