"""Пробы машины ходят за фактами в среду и судят их правилами домена."""

from tests.fakes.health_environment import FakeHealthEnvironment
from torrcast.domain.ffmpeg_pace import FfmpegPace
from torrcast.usecases.host_checkup import HostCheckup


def test_a_missing_terminal_never_asks_about_the_input_mode() -> None:
    """Терминала нет - спрашивать режим ввода не у чего, и строка про дефолты."""
    environment = FakeHealthEnvironment(tty=False, utf8=True)
    line, ok = HostCheckup(environment).terminal()
    assert ok and "no terminal" in line, line


def test_a_living_terminal_reports_its_utf8_mode() -> None:
    line, ok = HostCheckup(FakeHealthEnvironment(utf8=False)).terminal()
    assert ok and "we turn it on" in line, line


def test_the_locale_line_carries_both_the_charset_and_the_variables() -> None:
    environment = FakeHealthEnvironment(charset="utf-8", variables="LANG=ru_RU.UTF-8")
    line, ok = HostCheckup(environment).locale()
    assert ok and "utf-8" in line and "LANG=ru_RU.UTF-8" in line


def test_a_dead_ffmpeg_is_never_asked_for_its_version() -> None:
    """Программа не запускается - версии у неё не спрашиваем вовсе."""
    environment = FakeHealthEnvironment(pace=None, version="не спросят")
    line, ok = HostCheckup(environment).ffmpeg()
    assert not ok and "does not run" in line, line
    assert "не спросят" not in line


def test_a_living_ffmpeg_is_judged_by_its_measured_pace() -> None:
    """TC-1048: приговор - по секундам живого прогона, а не по номеру версии."""
    inert_burst = FfmpegPace(baseline_seconds=0.1, burst_seconds=7.7, entry_seconds=0.1)
    environment = FakeHealthEnvironment(pace=inert_burst, version="ffmpeg 8.0.1")
    assert HostCheckup(environment).ffmpeg()[1] is False
    assert HostCheckup(FakeHealthEnvironment()).ffmpeg()[1] is True
