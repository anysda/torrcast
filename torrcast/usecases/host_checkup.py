"""Пробы ``cast doctor`` про саму машину: терминал, локаль и ffmpeg.

Зовёт сценарий :mod:`torrcast.usecases.doctor`, факты берёт у порта среды.
"""

from torrcast.domain.health_verdict import HealthLine
from torrcast.domain.host_health import HostHealth
from torrcast.ports.health_environment import HealthEnvironment


class HostCheckup:
    """Три первых строки самопроверки: они не зависят ни от одной службы вокруг."""

    def __init__(self, environment: HealthEnvironment) -> None:
        self._environment = environment

    def terminal(self) -> HealthLine:
        """Терминал и режим ``IUTF8``: без него ssh ломает забой на кириллице."""
        if not self._environment.has_terminal():
            return HostHealth.terminal(False, None)
        return HostHealth.terminal(True, self._environment.terminal_utf8())

    def locale(self) -> HealthLine:
        """Кодировка: русские названия и ключи состояния должны переживать запись в файл."""
        return HostHealth.locale(self._environment.encoding(), self._environment.locale_env())

    def ffmpeg(self) -> HealthLine:
        """ffmpeg и ``-readrate_initial_burst``; версию спрашиваем только у живого."""
        help_text = self._environment.ffmpeg_help()
        version = self._environment.ffmpeg_version() if help_text is not None else None
        return HostHealth.ffmpeg(help_text, version)
