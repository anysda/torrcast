"""Чей подъём сейчас идёт: запуск ставит свою метку, и ожидание картинки её сверяет.

Ставит метку запуск показа (:func:`torrcast.usecases.playback._launch._launch`), сверяет
ожидание картинки (:func:`torrcast.usecases.playback._launch._await_playing`) и возврат
места (:func:`torrcast.usecases.playback.place_kept.place_kept`).
"""

from __future__ import annotations

import contextlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

#: Файл метки в каталоге показа. Уборка упаковщика его не трогает: она снимает только
#: сегменты, плейлисты и заголовки (:func:`torrcast.adapters.stream_pack.hls_dir._paths`).
OWNER_FILE = "launch.owner"

type SegmentMarks = frozenset[tuple[str, int, int, int, int, int]]


def _segment_marks(out: Path) -> SegmentMarks:
    """Идентичности сегментов, а не только общие для всех показов имена."""
    marks: set[tuple[str, int, int, int, int, int]] = set()
    for pattern in ("v*.ts", "v*.m4s"):
        with contextlib.suppress(OSError):
            for path in out.glob(pattern):
                with contextlib.suppress(OSError):
                    stat = path.stat()
                    marks.add(
                        (
                            path.name,
                            stat.st_dev,
                            stat.st_ino,
                            stat.st_size,
                            stat.st_mtime_ns,
                            stat.st_ctime_ns,
                        )
                    )
    return frozenset(marks)


@dataclass(frozen=True)
class LaunchOwner:
    """Метка одного подъёма в каталоге показа; пустая - каталог недоступен, и мы не знаем.

    🔴 Имя юнита одно на машину, и мост веба, бот и консоль гасят и поднимают его по
    очереди. Метка ставится ДО того, как запуск погасит прошлый юнит: ожидание, чей юнит
    погашен, видит чужую метку раньше, чем мёртвый юнит, - иначе оно звало бы чужой
    подъём своим отказом («показ не запустился», прод 11-09-2026).
    """

    out: Path
    token: str = ""
    segments: SegmentMarks = frozenset()

    @classmethod
    def claim(cls, out: Path) -> LaunchOwner:
        """Поставить метку своего подъёма поверх любой прежней."""
        token = f"{os.getpid()}:{uuid.uuid4().hex}"
        try:
            out.mkdir(parents=True, exist_ok=True)
            (out / OWNER_FILE).write_text(token)
        except OSError:
            return cls(out)
        return cls(out, token)

    def taken_over(self) -> bool:
        """Снял ли этот подъём чужой запуск: метка на месте, и она не наша.

        Пустая метка или нечитаемый файл - не знаем, и ожидание идёт прежним путём.
        """
        if not self.token:
            return False
        with contextlib.suppress(OSError):
            return (self.out / OWNER_FILE).read_text() != self.token
        return False

    def separate_segments(self) -> LaunchOwner:
        """Запомнить остаток до подъёма юнита, чтобы не назвать его своей готовностью."""
        return LaunchOwner(self.out, self.token, _segment_marks(self.out))

    def has_new_segment(self) -> bool:
        """Появился ли сегмент, которого не было после остановки прошлого юнита."""
        return bool(_segment_marks(self.out) - self.segments)


def _new_segment(out: Path, owner: LaunchOwner | None) -> bool:
    """Свежий сегмент этого подъёма; без метки сохранить прежний прямой договор."""
    return owner.has_new_segment() if owner is not None else bool(_segment_marks(out))
