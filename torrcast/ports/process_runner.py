"""Запускает для сценариев внешние программы."""

from collections.abc import Sequence
from typing import Protocol

from torrcast.domain.process_result import ProcessResult


class ProcessRunner(Protocol):
    def run(self, command: Sequence[str]) -> ProcessResult: ...
