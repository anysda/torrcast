"""Заводит тестам подставной приёмник и помнит, каким его просили."""

from dataclasses import dataclass, field
from typing import Literal

from tests.fakes.receiver import FakeReceiver
from torrcast.domain.position import Position
from torrcast.domain.profile import CAUTIOUS, Profile


@dataclass
class FakeReceivers:
    #: Один и тот же приёмник на весь юнит: соединение с ТВ живёт дольше серии, и
    #: второй приёмник на стыке серий - это два сендера сразу.
    receiver: FakeReceiver = field(default_factory=lambda: FakeReceiver(Position(0.0, 0.0)))
    #: Каким его просили: вид, адрес, доверенный корень и профиль устройства.
    asked: list[tuple[str, str, str, Profile]] = field(default_factory=list)

    def __call__(
        self,
        kind: Literal["chromecast", "mock"],
        address: str = "",
        ca: str = "",
        profile: Profile = CAUTIOUS,
    ) -> FakeReceiver:
        self.asked.append((kind, address, ca, profile))
        return self.receiver
