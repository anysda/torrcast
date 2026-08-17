"""Выбор приёмника по имени: живой Chromecast или сухой приёмник приёмки.

Зовёт его композиционный корень (:mod:`torrcast.runtime.wire`), и только он."""

from __future__ import annotations

from typing import Literal, cast

from torrcast.adapters.chromecast.cast.chromecast_receiver import ChromecastReceiver
from torrcast.adapters.chromecast.mock.mock_receiver import MockReceiver
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.trust_anchor import trust_anchor
from torrcast.ports.receiver import Receiver

ReceiverKind = Literal["chromecast", "mock"]


def make_receiver(
    kind: ReceiverKind, address: str = "", ca: str = "", profile: Profile = CAUTIOUS
) -> Receiver:
    """Приёмник по имени: живой Chromecast или сухой приёмник автономной приёмки."""
    if kind == "mock":
        return cast(Receiver, MockReceiver(trust_anchor(ca) if ca else "", profile=profile))
    return ChromecastReceiver(address, profile=profile)
