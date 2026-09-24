"""Полка найденных постеров на диске; зовёт картинка карточки плеера."""

from __future__ import annotations

import contextlib
import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Final

from hass.picture_size import picture_size
from torrcast.adapters.filesystem.state.state_path import state_path
from torrcast.domain.facts.lying_down import lying_down

#: Shape rule stamped into every new poster filename. Bump whenever shelf acceptance changes.
RULE: Final = 1


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
        """Read a current poster; judge and stamp an older file once from its bytes."""
        with contextlib.suppress(OSError):
            return self._where(identity).read_bytes()
        old = self._old(identity)
        if old is None:
            return None
        with contextlib.suppress(OSError):
            body = old.read_bytes()
            size = picture_size(body)
            if size is None or lying_down(*size) is not False:
                return None
            current = self._where(identity)
            old.replace(current)
            return body
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
        return self.home() / f"{self._stem(identity)}.r{RULE}"

    def _old(self, identity: str) -> Path | None:
        """Newest file stamped by an older rule, including the unstamped original shelf."""
        home, stem = self.home(), self._stem(identity)
        candidates: list[tuple[int, Path]] = []
        plain = home / stem
        if plain.is_file():
            candidates.append((0, plain))
        with contextlib.suppress(OSError):
            for path in home.glob(f"{stem}.r*"):
                with contextlib.suppress(ValueError):
                    rule = int(path.name.rsplit(".r", 1)[1])
                    if rule < RULE and path.is_file():
                        candidates.append((rule, path))
        if not candidates:
            return None
        return max(candidates, key=lambda item: item[0])[1]

    @staticmethod
    def _stem(identity: str) -> str:
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


__all__ = ["RULE", "PosterShelf"]
