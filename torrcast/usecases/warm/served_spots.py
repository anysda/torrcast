"""Сеансовая память о точечных перекодах прогретого каталога."""

from __future__ import annotations

from pathlib import Path

from torrcast.usecases.warm._vault_disk import _spot_marks


class ServedSpots(set[int]):
    """Метки для раздачи: один снимок диска, затем живые сообщения прогрева."""

    def __init__(self, directory: Path) -> None:
        super().__init__(_spot_marks(directory))
        self._directory = directory

    def mark(self, slot: int) -> None:
        """Поставить метку на диск и сразу показать её раздаче."""
        (self._directory / f"v{slot}.rec").touch()
        self.add(slot)
