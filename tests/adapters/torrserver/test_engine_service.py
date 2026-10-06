"""Служба TorrServer у менеджера служб: что спрашивается и чем она поднимается заново."""

from __future__ import annotations

import subprocess

from torrcast.adapters.torrserver.engine_service import EngineService


class _Calls:
    """Менеджер служб, отвечающий заданным выводом и помнящий вызовы."""

    def __init__(self, out: str = "", code: int = 0) -> None:
        self.out = out
        self.code = code
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, tool: str, *args: str) -> subprocess.CompletedProcess[str]:
        self.calls.append((tool, *args))
        return subprocess.CompletedProcess([tool, *args], self.code, self.out, "")


def _missing(tool: str, *args: str) -> subprocess.CompletedProcess[str]:
    raise FileNotFoundError(tool)


def test_a_hung_service_is_killed_before_it_is_started_again() -> None:
    systemd = _Calls()

    assert EngineService("linux", systemd=systemd).restart()
    assert systemd.calls == [
        ("systemctl", "kill", "--signal=KILL", "torrserver.service"),
        ("systemctl", "restart", "torrserver.service"),
    ]


def test_only_a_loaded_unit_counts_as_our_service() -> None:
    assert EngineService("linux", systemd=_Calls("loaded\n")).known()
    assert not EngineService("linux", systemd=_Calls("not-found\n")).known()
    assert not EngineService("linux", systemd=_missing).known()


def test_the_unit_state_is_what_systemd_says() -> None:
    assert EngineService("linux", systemd=_Calls("activating\n")).state() == "activating"
    assert EngineService("linux", systemd=_missing).state() == ""


def test_on_a_mac_the_job_is_kickstarted() -> None:
    launchd = _Calls()

    assert EngineService("darwin", launchd=launchd).restart()
    assert launchd.calls[0][:3] == ("launchctl", "kickstart", "-k")
    assert launchd.calls[0][3].endswith("/org.torrcast.torrserver")
