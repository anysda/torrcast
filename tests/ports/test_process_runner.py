"""Проверяет контракт запуска процессов и поведение фейка."""

from tests.fakes.process_runner import FakeProcessRunner
from torrcast.domain.process_result import ProcessResult
from torrcast.ports.process_runner import ProcessRunner


def test_fake_records_command_and_returns_result() -> None:
    result = ProcessResult(1, stderr="failed")
    fake = FakeProcessRunner(result)
    port: ProcessRunner = fake
    assert port.run(["tool", "arg"]) == result
    assert fake.commands == [("tool", "arg")]
