"""Проверяет ffprobe через фейк порта запуска процессов."""

from tests.fakes.process_runner import FakeProcessRunner
from torrcast.adapters.ffprobe.ffprobe_prober import FfprobeProber
from torrcast.domain.process_result import ProcessResult


def test_runs_ffprobe_with_configured_timeout() -> None:
    runner = FakeProcessRunner(ProcessResult(0, '{"format":{"duration":"3"}}'))
    media = FfprobeProber(runner, timeout=12.0).probe("http://source")
    assert media.duration == 3.0
    assert runner.commands[0][0] == "ffprobe"
    assert runner.commands[0][-1] == "http://source"
    assert runner.timeouts == [12.0]
