"""Возвращает тестам приёмники и запоминает условия поиска."""

from dataclasses import dataclass, field

from torrcast.domain.receiver_info import ReceiverInfo


@dataclass
class FakeReceiverFinder:
    receivers: list[ReceiverInfo] = field(default_factory=list)
    names: list[str | None] = field(default_factory=list)

    def find(self, name: str | None = None) -> list[ReceiverInfo]:
        self.names.append(name)
        return list(self.receivers)
