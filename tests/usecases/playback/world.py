"""Поддельный мир показа: настоящая сетка и настоящие кодировщики, но без сети и ffmpeg.

Общий инвентарь зеркал пакета. Договор медиатракта тут не пересказывается подделкой -
зеркала берут НАСТОЯЩИЕ классы адаптера и сверяют их с названным договором показа.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from torrcast.adapters.stream_pack.grid import Grid
from torrcast.domain.film_keys import FilmKeys


def grid(duration: float = 300.0, gop: float = 2.0, step: float = 10.0) -> Grid:
    """Настоящая сетка по опорным кадрам: ровно та, что ходит по боевому пути.

    Карту сетка несёт с собой (:attr:`Grid.keys`) - так её собирает боевой
    :func:`~torrcast.adapters.stream_pack.grid_for.grid_for`, и по ней кодировщик считает вес
    куска. Забудь это зеркало - и профиль тяжести оказался бы ровным там, где боевой путь
    строит его по карте.
    """
    keys = film_keys(duration, gop)
    return replace(Grid.on_keyframes(keys.at, duration, step, sizes=keys.offset), keys=keys)


def film_keys(duration: float = 300.0, gop: float = 2.0) -> FilmKeys:
    """Карта опорных кадров ровного материала: кадр каждые ``gop`` секунд."""
    at = [round(n * gop, 3) for n in range(int(duration / gop) + 1)]
    offset = [n * 1_000_000 for n in range(len(at))]
    return FilmKeys(at=at, duration=duration, offset=offset)


@dataclass
class FakeShow:
    """Юнит показа под наблюдением зеркала: жив ли он и что он о себе говорит."""

    alive: bool = True
    reason: str = "юнит ещё идёт к картинке"
    stopped: int = 0
    name: str = "кино"

    @property
    def key(self) -> str:
        return self.name

    def active(self) -> bool:
        return self.alive

    def why(self) -> str:
        return self.reason

    def stop(self) -> None:
        self.stopped += 1
        self.alive = False


@dataclass
class FakeProgress:
    """Индикатор, который только записывает, что ему сказали."""

    phases: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def phase(self, text: str) -> None:
        self.phases.append(text)

    def note(self, text: str) -> None:
        self.notes.append(text)

    def stop(self) -> None:
        return None

    def __enter__(self) -> FakeProgress:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def touch_segment(out: Path, slot: int = 0) -> None:
    """Положить в каталог показа кусок: для ожидания картинки это «упаковка пошла»."""
    out.mkdir(parents=True, exist_ok=True)
    (out / f"v{slot}.ts").write_bytes(b"x")
