"""Ищет приёмники в сети двумя способами сразу и показывает живой прогресс поиска.
Даёт их сценарию настройки ТВ (:class:`torrcast.usecases.configure.Configure`).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from torrcast.adapters.chromecast import scan as _scan
from torrcast.domain.receiver_info import ReceiverInfo
from torrcast.ports.progress import progress as progress_bar


class NetworkReceiverFinder:
    """Реализация порта поиска поверх :func:`torrcast.adapters.chromecast.scan.find`.

    Про подсети, которые обойти не удалось, поиск молчать не вправе - их объяснение
    едет отдельно от списка (:meth:`notes`) и печатается сценарием перед меню.
    """

    def __init__(self, discover: Callable[[], Any] | None = None) -> None:
        self._discover = discover
        self._notes: list[str] = []

    def find(self, name: str | None = None) -> list[ReceiverInfo]:
        # Обход спрашивается у модуля в момент поиска: подмену сети ставят именно на него.
        discover = self._discover if self._discover is not None else _scan.find
        with progress_bar() as progress:
            progress.phase("ищу приёмники в сети")
            found = discover()
        self._notes = list(found.notes)
        devices = [
            ReceiverInfo(name=device.name, address=device.address, model=device.model)
            for device in found.devices
        ]
        if name is None:
            return devices
        return [device for device in devices if device.name.casefold() == name.casefold()]

    def notes(self) -> list[str]:
        """Почему список мог оказаться неполным; известно это только после поиска."""
        return list(self._notes)
