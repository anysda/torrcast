"""Гасит transient-юнит показа; зовут команды ``cast stop`` и запуск нового показа."""

from __future__ import annotations

from torrcast.adapters.systemd._systemd_call import SystemdCall, _systemd
from torrcast.domain.unit_naming import _UNIT_NAME


def stop_play_unit(unit: str = _UNIT_NAME, *, call: SystemdCall = _systemd) -> None:
    """Погасить transient-юнит и дождаться его смерти: по SIGTERM сторож дописывает
    позицию в state. Отсутствие юнита ошибкой не считается.

    ``call`` - чем звать systemd; боевое умолчание одно, и меняет его только стенд.
    """
    call("systemctl", "stop", unit)
