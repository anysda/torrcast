"""Ищет приёмники через штатный discovery pychromecast."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from torrcast.adapters.chromecast.cast.hush_cosmetic_noise import hush_cosmetic_noise
from torrcast.domain.receiver_info import ReceiverInfo


class PyChromecastReceiverFinder:
    """Реализация порта поиска с прежним четырёхсекундным ожиданием mDNS."""

    def __init__(self, discover: Callable[..., tuple[list[Any], Any]] | None = None) -> None:
        self._discover = discover

    def find(self, name: str | None = None) -> list[ReceiverInfo]:
        hush_cosmetic_noise()
        discover = self._discover
        if discover is None:
            import pychromecast

            discover = pychromecast.get_chromecasts
        casts, browser = discover(timeout=4.0)
        try:
            found = []
            for cast in casts:
                cast_name = str(getattr(cast, "name", "") or "")
                if name and cast_name.casefold() != name.casefold():
                    continue
                host = str(getattr(cast, "host", "") or "")
                model = str(getattr(cast, "model_name", "") or "")
                found.append(ReceiverInfo(cast_name, host, model))
            return found
        finally:
            browser.stop_discovery()

    def notes(self) -> list[str]:
        """Штатный discovery про пропущенное молчит: пояснять ему нечего."""
        return []
