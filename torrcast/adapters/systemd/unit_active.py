"""Отвечает, идёт ли показ прямо сейчас; спрашивают ``cast status`` и щупы."""

from __future__ import annotations

from torrcast.adapters.systemd._systemd_call import SystemdCall, _systemd
from torrcast.domain.unit_naming import _UNIT_NAME


def unit_active(unit: str = _UNIT_NAME, *, call: SystemdCall = _systemd) -> bool:
    """Идёт ли показ прямо сейчас.

    ``call`` - чем звать systemd; боевое умолчание одно, и меняет его только стенд.
    """
    return call("systemctl", "is-active", unit).stdout.strip() == "active"
