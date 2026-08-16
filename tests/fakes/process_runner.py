"""Изображает для тестов запуск внешних программ и записывает команды."""

from collections.abc import Sequence
from dataclasses import dataclass, field

from torrcast.domain.process_result import ProcessResult


@dataclass
class FakeProcessRunner:
    result: ProcessResult = field(default_factory=lambda: ProcessResult(0))
    commands: list[tuple[str, ...]] = field(default_factory=list)
    timeouts: list[float | None] = field(default_factory=list)

    def run(self, command: Sequence[str], timeout: float | None = None) -> ProcessResult:
        self.commands.append(tuple(command))
        self.timeouts.append(timeout)
        return self.result
