"""Служба TorrServer глазами менеджера служб: знает ли он её и как поднять её заново.

Служба одна на машину, и ставит её ``install.sh``: юнит ``torrserver.service`` у systemd,
задание ``org.torrcast.torrserver`` у launchd. Других служб движка у продукта нет, и
чужой TorrServer (свой адрес в настройках) этот модуль не трогает вовсе: поднимать
заново можно только то, что поставили мы сами.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Final

from torrcast.adapters.launchd._launchd_call import LaunchdCall, _domain, _launchd, _running
from torrcast.adapters.systemd._systemd_call import SystemdCall, _systemd

UNIT: Final = "torrserver.service"
LABEL: Final = "org.torrcast.torrserver"

#: Состояния юнита, в которых systemd службу держит: работает, поднимается сам после
#: падения (``Restart=on-failure`` ждёт ``RestartSec``) или перечитывает настройки.
HELD: Final = frozenset({"active", "activating", "reloading"})


class EngineService:
    """Юнит или задание движка раздач; ``call`` меняет только стенд."""

    def __init__(
        self,
        platform: str = sys.platform,
        systemd: SystemdCall = _systemd,
        launchd: LaunchdCall = _launchd,
    ) -> None:
        self._mac = platform == "darwin"
        self._systemd = systemd
        self._launchd = launchd

    def known(self) -> bool:
        """Знает ли менеджер служб наш TorrServer вообще; нет службы - поднимать нечего."""
        try:
            if self._mac:
                return self._launchd("launchctl", "print", self._job()).returncode == 0
            done = self._systemd("systemctl", "show", "-p", "LoadState", "--value", UNIT)
            return done.stdout.strip() == "loaded"
        except (OSError, subprocess.SubprocessError):  # менеджера служб нет (песочница)
            return False

    def coming(self) -> bool:
        """Держит ли менеджер службу сейчас: работает или поднимается сам после падения."""
        try:
            if self._mac:
                return _running(self._launchd("launchctl", "print", self._job()).stdout)
            return self._systemd("systemctl", "is-active", UNIT).stdout.strip() in HELD
        except (OSError, subprocess.SubprocessError):
            return False

    def restart(self) -> bool:
        """Убить процесс службы и поднять новый; ``False`` - менеджер отказал.

        🔴 Повисший TorrServer убивается KILL, а не TERM. На TERM служба закрывает
        клиента раздач, а его замок держит как раз то, что повисло: ``restart`` ждал бы
        ``TimeoutStopSec`` (у systemd 90 с) и только потом бил бы KILL сам.
        """
        try:
            if self._mac:
                done = self._launchd("launchctl", "kickstart", "-k", self._job())
                return done.returncode == 0
            self._systemd("systemctl", "kill", "--signal=KILL", UNIT)
            return self._systemd("systemctl", "restart", UNIT).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    @staticmethod
    def _job() -> str:
        return f"{_domain()}/{LABEL}"


__all__ = ["EngineService"]
