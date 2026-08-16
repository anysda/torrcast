"""Сценарий doctor сообщает все проверки и итог."""

from dataclasses import dataclass

from tests.fakes.configuration_source import FakeConfigurationSource
from tests.fakes.console import FakeConsole
from torrcast.domain.settings import Settings
from torrcast.usecases.doctor import Doctor


@dataclass
class FakeHealthChecks:
    lines: list[tuple[str, bool]]

    def check(self, settings: Settings) -> list[tuple[str, bool]]:
        assert settings.tv == "192.0.2.1"
        return self.lines


def test_doctor_prints_success() -> None:
    console = FakeConsole()
    doctor = Doctor(
        FakeConfigurationSource(Settings(tv="192.0.2.1")),
        FakeHealthChecks([("ок      ffmpeg", True)]),
        console,
    )

    assert doctor.run() == 0
    assert console.messages == ["ок      ffmpeg", "", "всё в порядке"]


def test_doctor_counts_failed_checks() -> None:
    console = FakeConsole()
    doctor = Doctor(
        FakeConfigurationSource(Settings(tv="192.0.2.1")),
        FakeHealthChecks([("плохо   ffmpeg", False), ("плохо   ТВ", False)]),
        console,
    )

    assert doctor.run() == 2
    assert console.messages[-1] == "проблем: 2 - смотри строки «плохо» выше"
