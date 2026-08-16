"""Запускает внешние команды для адаптеров служб."""

import subprocess
from collections.abc import Sequence

from torrcast.domain.process_result import ProcessResult


class SubprocessRunner:
    """Реализация порта запуска процесса с прежним таймаутом."""

    def run(self, command: Sequence[str]) -> ProcessResult:
        done = subprocess.run(command, capture_output=True, text=True, check=False, timeout=60)
        return ProcessResult(done.returncode, done.stdout, done.stderr)
