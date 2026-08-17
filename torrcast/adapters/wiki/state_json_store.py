"""JSON-файл, чей путь спрашивается на каждом обращении; им живёт кэш справки."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from torrcast.adapters.wiki.json_file_store import JsonFileStore


class StateJsonStore:
    """Хранилище рядом с состоянием: каталог состояния меняется на лету.

    Прибитый в конструктор путь тут не годится: ``TORRCAST_STATE`` разводит запуски по
    разным каталогам, и кэш обязан ехать за состоянием, а не за первым обращением.
    """

    def __init__(self, where: Callable[[], Path]) -> None:
        self.where = where

    def read(self) -> dict[str, Any]:
        return JsonFileStore(self.where()).read()

    def write(self, value: dict[str, Any]) -> None:
        JsonFileStore(self.where()).write(value)
