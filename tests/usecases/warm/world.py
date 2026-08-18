"""Поддельная среда прогрева и мелкий инвентарь: общее для зеркал пакета прогрева.

Часы тут ручные, сна нет вовсе, а телеметрия складывается в списки: зеркала обязаны
мерить решение прогрева, а не терпеливость машины.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import torrcast.usecases.warm._state as _state
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.usecases.warm.vault import Vault
from torrcast.usecases.warm.warmer import Warmer

if TYPE_CHECKING:
    import pytest


@dataclass
class FakeEnvironment:
    """Часы, диск и телеметрия прогрева под наблюдением зеркала."""

    now: float = 1000.0
    slept: list[float] = field(default_factory=list)
    marks: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    events: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = field(default_factory=list)
    removed: list[Path] = field(default_factory=list)
    stamp: float = 1_700_000_000.0
    naps: int = 1000

    def epoch(self) -> float:
        return self.stamp

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds
        if len(self.slept) > self.naps:
            raise AssertionError(
                f"прогрев уснул {len(self.slept)} раз подряд: ожидание не кончается. "
                "Самое долгое честное ожидание тут - START_GRACE по полсекунды, "
                "то есть под сотню снов, так что тысяча - это уже вечный цикл."
            )

    def remove_tree(self, path: object) -> None:
        import shutil

        where = Path(str(path))
        self.removed.append(where)
        shutil.rmtree(where, ignore_errors=True)

    def emit(self, event: str, *args: object, **facts: object) -> None:
        self.events.append((event, args, dict(facts)))

    def mark(self, name: str, **facts: object) -> None:
        self.marks.append((name, dict(facts)))

    def named(self, name: str) -> dict[str, Any]:
        """Поля метки с таким именем; нет метки - пустой словарь."""
        for mark, facts in self.marks:
            if mark == name:
                return facts
        return {}


def world(monkeypatch: pytest.MonkeyPatch) -> FakeEnvironment:
    """Подставить прогреву поддельную среду на время одного теста."""
    fake = FakeEnvironment()
    monkeypatch.setattr(_state, "_environment", fake)
    return fake


def grid(duration: float = 60.0, step: float = 10.0) -> Grid:
    """Ровная сетка: шесть кусков по десять секунд."""
    return Grid.uniform(duration, step)


def vault(root: Path, key: str = "k", budget: int = 1 << 30, floor: int = 0) -> Vault:
    """Каталог прогретого с заведомо просторным бюджетом и без запаса раздела."""
    store = Vault(root=root / "warm", key=key, budget=budget, floor=floor)
    store.dir.mkdir(parents=True, exist_ok=True)
    return store


def lay(store: Vault, slot: int, size: int = 1024) -> Path:
    """Положить в каталог прогретого кусок нужного веса."""
    path = store.path(slot)
    path.write_bytes(b"x" * size)
    return path


def warmer(root: Path, **kwargs: Any) -> Warmer:
    """Прогрев на ровной сетке поверх свежего каталога."""
    lines = kwargs.pop("grid", None) or grid()
    store = kwargs.pop("vault", None) or vault(root)
    return Warmer(source="src", audio=0, grid=lines, vault=store, **kwargs)
