"""Достаёт ключ состояния играющего показа из описания юнита; зовёт ``cast status``."""

from __future__ import annotations

from torrcast.adapters.systemd._systemd_call import SystemdCall, _systemd
from torrcast.domain.unit_naming import _UNIT_NAME, _UNIT_TAG


def unit_key(unit: str = _UNIT_NAME, *, call: SystemdCall = _systemd) -> str:
    """Ключ состояния играющего показа — из ``--description`` юнита. Свежайшая запись в
    state для этого не годится: рядом мог писать другой ход, и ``status`` соврал бы.

    ``call`` - чем звать systemd; боевое умолчание одно, и меняет его только стенд.
    """
    found = call("systemctl", "show", unit, "-p", "Description", "--value").stdout.strip()
    return found[len(_UNIT_TAG) :].strip() if found.startswith(_UNIT_TAG) else ""
