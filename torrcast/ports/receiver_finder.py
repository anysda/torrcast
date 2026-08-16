"""Ищет для сценариев приёмники воспроизведения в локальной сети."""

from typing import Protocol

from torrcast.domain.receiver_info import ReceiverInfo


class ReceiverFinder(Protocol):
    def find(self, name: str | None = None) -> list[ReceiverInfo]: ...
    def notes(self) -> list[str]: ...
