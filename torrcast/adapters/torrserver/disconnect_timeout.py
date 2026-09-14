"""Через сколько секунд без читателей TorrServer закрывает раздачу: читается один раз."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final

from torrcast.domain.infra_error import InfraError

#: Умолчание TorrServer (``server/settings/btsets.go``): ноль в настройках значит 30.
DEFAULT: Final = 30.0

_READ: dict[str, float] = {}


def disconnect_timeout(base_url: str, post: Callable[[str, dict[str, Any]], Any]) -> float:
    """``TorrentDisconnectTimeout`` службы по адресу; не прочиталось - умолчание."""
    if base_url not in _READ:
        try:
            payload = post("/settings", {"action": "get"})
            seconds = float(payload.get("TorrentDisconnectTimeout") or 0)
        except (InfraError, AttributeError, TypeError, ValueError):
            seconds = 0.0
        _READ[base_url] = seconds if seconds > 0 else DEFAULT
    return _READ[base_url]
