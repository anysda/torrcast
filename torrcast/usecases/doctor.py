"""Выполняет самопроверку окружения и печатает общий вердикт."""

from torrcast.ports.configuration_source import ConfigurationSource
from torrcast.ports.console import Console
from torrcast.ports.health_checks import HealthChecks


class Doctor:
    """Сценарий команды ``cast doctor``."""

    def __init__(
        self,
        configuration: ConfigurationSource,
        checks: HealthChecks,
        console: Console,
    ) -> None:
        self._configuration = configuration
        self._checks = checks
        self._console = console

    def run(self) -> int:
        """Печатает проверки и возвращает прежний код команды."""
        bad = 0
        for line, ok in self._checks.check(self._configuration.load()):
            self._console.write(line)
            bad += 0 if ok else 1
        self._console.write("")
        verdict = "всё в порядке" if not bad else f"проблем: {bad} - смотри строки «плохо» выше"
        self._console.write(verdict)
        return 0 if not bad else 2
