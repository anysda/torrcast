"""Гасит transient-юнит показа; зовут команды ``cast stop`` и запуск нового показа."""

from __future__ import annotations

from torrcast.adapters.systemd._systemd_call import _systemd
from torrcast.domain.unit_naming import _UNIT_NAME


def stop_play_unit(unit: str = _UNIT_NAME) -> None:
    """Погасить transient-юнит и дождаться его смерти: по SIGTERM сторож дописывает
    позицию в state. Отсутствие юнита ошибкой не считается.
    """
    _systemd("systemctl", "stop", unit)
