"""Отвечает, идёт ли показ прямо сейчас; спрашивают ``cast status`` и щупы."""

from __future__ import annotations

from torrcast.adapters.systemd._systemd_call import _systemd
from torrcast.domain.unit_naming import _UNIT_NAME


def unit_active(unit: str = _UNIT_NAME) -> bool:
    """Идёт ли показ прямо сейчас."""
    return _systemd("systemctl", "is-active", unit).stdout.strip() == "active"
