"""Полка найденных постеров на диске; зовёт картинка карточки плеера."""

from __future__ import annotations

import contextlib
import hashlib
from collections.abc import Callable
from pathlib import Path

from torrcast.adapters.filesystem.state.state_path import state_path


def _beside_state() -> Path:
    """Постеры лежат рядом с состоянием и справкой - и переезжают вместе с ними."""
    return state_path().with_name("posters")


class PosterShelf:
    """Постер картины на диске, чтобы не спрашивать Википедию об одном и том же.

    🔴 Кладётся сюда ТОЛЬКО постер. Кадр показа, которым карточка закрывается, когда
    постера не нашлось, на полку не попадает никогда: полка отвечает раньше сети, и
    записанный на неё кадр означал бы, что у этой картины постера не будет уже никогда -
    даже когда английская статья про неё появится. Запасной путь обязан оставаться
    запасным, а не становиться ответом.

    Не вышло прочитать или записать - молчим: это не путь показа, и пустая полка равна
    полке, которой нет. Спрашивают её один раз на картину, а промах стоит трёх запросов
    к Википедии, а не сорванного показа.
    """

    def __init__(self, home: Callable[[], Path] = _beside_state) -> None:
        self.home = home

    def read(self, identity: str) -> bytes | None:
        """Что лежит на полке под этой картиной; ничего - ``None``."""
        with contextlib.suppress(OSError):
            return self._where(identity).read_bytes()
        return None

    def write(self, identity: str, body: bytes) -> None:
        """Положить постер на полку под именем картины."""
        with contextlib.suppress(OSError):
            home = self.home()
            home.mkdir(parents=True, exist_ok=True)
            self._where(identity).write_bytes(body)

    def _where(self, identity: str) -> Path:
        """Файл картины на полке. Имя - отпечаток, а не название.

        Название картины приезжает из раздачи и держит что угодно: косую черту, точки,
        двоеточие, письмо любой стороны света. Имя файла из такой строки - это чужой
        путь в чужом каталоге, а отпечаток - всегда одно и то же короткое имя.
        """
        return self.home() / hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
