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
