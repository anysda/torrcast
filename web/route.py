"""Один маршрут страницы: кто спрашивает, что спрашивает и кто отвечает."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from web.answer import Answer
from web.request import Request


@dataclass(frozen=True, slots=True)
class Route:
    """Строка таблицы маршрутов (:func:`web.routes.routes`).

    ``prefix`` заведён не для красоты: раздача файлов отвечает на всё, что начинается с
    ``/static/``, а карточка соседнего захода - на ``/api/card/{key}``. Без него такой
    маршрут пришлось бы разбирать в сервере, то есть править чужой файл.
    """

    method: str
    path: str
    answer: Callable[[Request], Answer]
    prefix: bool = False

    def takes(self, method: str, path: str) -> bool:
        """Этот ли маршрут отвечает: точным путём, а с :attr:`prefix` - его началом."""
        if method != self.method:
            return False
        return path.startswith(self.path) if self.prefix else path == self.path
