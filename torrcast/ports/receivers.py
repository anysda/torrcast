"""Заводит для сценариев приёмник показа: чем играть и на чём.

Какой приёмник нужен, знает сценарий - вид, адрес, доверенный корень для TLS и профиль
устройства, - а ЧЕМ его завести приходит от композиционного корня
(:mod:`torrcast.runtime.wire`).
"""

from typing import Literal, Protocol

from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.ports.receiver import Receiver


class Receivers(Protocol):
    """Что сценариям нужно от завода приёмника - и ничего сверх того."""

    def __call__(
        self,
        kind: Literal["chromecast", "mock"],
        address: str = "",
        ca: str = "",
        profile: Profile = CAUTIOUS,
    ) -> Receiver:
        """Приёмник вида ``kind``; ``ca`` пуст - показ едет без TLS."""
