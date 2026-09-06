"""Выбор приёмника по имени: живой Chromecast или сухой приёмник приёмки.

Зовёт его композиционный корень (:mod:`torrcast.runtime.wire`), и только он."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, cast

from torrcast.adapters.browser.browser_receiver import BrowserReceiver
from torrcast.adapters.chromecast.cast.chromecast_receiver import ChromecastReceiver
from torrcast.adapters.chromecast.mock.mock_receiver import MockReceiver
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.trust_anchor import trust_anchor
from torrcast.ports.receiver import Receiver

ReceiverKind = Literal["chromecast", "mock", "browser"]


def make_receiver(
    kind: ReceiverKind, address: str = "", ca: str = "", profile: Profile = CAUTIOUS
) -> Receiver:
    """Приёмник по имени: живой Chromecast, сухой приёмник приёмки или вкладка браузера.

    У ``browser`` ``address`` несёт не адрес устройства, а уже разрешённый каталог
    сегментов показа (:func:`torrcast.usecases.worker._worker_receivers`,
    :func:`torrcast.usecases.playback.hls_root.hls_root`): у вкладки нет сетевого
    адреса, и слот довода занят тем же способом, каким ``mock`` уже не смотрит на него.
    """
    if kind == "mock":
        return cast(Receiver, MockReceiver(trust_anchor(ca) if ca else "", profile=profile))
    if kind == "browser":
        return cast(Receiver, BrowserReceiver(Path(address), profile=profile))
    return ChromecastReceiver(address, profile=profile)
