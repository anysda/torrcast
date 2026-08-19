"""Зона пометок в имени раздачи: что там сказано про 3D и про приложения к фильму.

Наследует их :class:`torrcast.domain.release.Release`, и только он.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from torrcast.domain._name_data.data_1 import (
    _EXTRAS_RE,
    _EXTRAS_SURE_RE,
    _STEREO_LAYOUT_RE,
    _STEREO_RE,
    _TWO_D_RE,
    _WITH_EXTRAS_RE,
)
from torrcast.domain._release_fields import _ReleaseFields


@dataclass(frozen=True, slots=True)
class _ReleaseMarks(_ReleaseFields):
    """Метки имени раздачи судятся в зоне пометок, а не по всему имени целиком."""

    @property
    def untitled(self) -> str:
        """Имя раздачи без названия картины: зона пометок, по которой судят метки."""
        tail = self.raw_name
        for name in (self.title, self.original, *self.aliases):
            if name:
                tail = re.sub(f"(?<!\\w){re.escape(name)}(?!\\w)", " ", tail, flags=re.IGNORECASE)
        return tail

    @property
    def stereoscopic(self) -> bool:
        if _STEREO_LAYOUT_RE.search(self.raw_name):
            return True
        tail = self.untitled
        return bool(re.search("\\b3д\\b", self.raw_name, re.IGNORECASE)) or (
            not _TWO_D_RE.search(tail) and bool(_STEREO_RE.search(tail))
        )

    @property
    def extras_mark(self) -> str:
        """Метка приложения, сработавшая в зоне пометок; пусто - метки нет.

        Метка, перед которой стоит «+», приложением раздачу не делает: «фильм + доп
        материалы» - это фильм, к которому приложено, а не приложение само по себе.
        """
        tail = self.untitled
        for found in _EXTRAS_RE.finditer(tail):
            if not _WITH_EXTRAS_RE.search(tail[: found.start()]):
                return found.group(0)
        return ""

    @property
    def extras(self) -> bool:
        return bool(self.extras_mark)

    @property
    def extras_sure(self) -> bool:
        return self.extras and bool(_EXTRAS_SURE_RE.search(self.untitled))
