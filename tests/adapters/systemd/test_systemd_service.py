"""Проверяет команды службы через фейк порта процессов."""

from tests.fakes.process_runner import FakeProcessRunner
from torrcast.adapters.systemd.systemd_service import SystemdService
from torrcast.domain.process_result import ProcessResult


def test_reads_active_state() -> None:
    runner = FakeProcessRunner(ProcessResult(0, "active\n"))

    assert SystemdService(runner, system=False).active("torrcast-play")
    assert runner.commands == [("systemctl", "--user", "is-active", "torrcast-play")]
