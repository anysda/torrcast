"""Возвращает тестам приёмники, их пояснения и запоминает условия поиска."""

from dataclasses import dataclass, field

from torrcast.domain.receiver_info import ReceiverInfo


@dataclass
class FakeReceiverFinder:
    receivers: list[ReceiverInfo] = field(default_factory=list)
    names: list[str | None] = field(default_factory=list)
    remarks: list[str] = field(default_factory=list)

    def find(self, name: str | None = None) -> list[ReceiverInfo]:
        self.names.append(name)
        return list(self.receivers)

    def notes(self) -> list[str]:
        return list(self.remarks)
