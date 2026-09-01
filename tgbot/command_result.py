"""Исполняет CLI для Telegram и сохраняет его словесный отказ вместе с выводом."""

from __future__ import annotations

import contextlib
import io
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TextIO

_Command = Callable[[Sequence[str] | None], int]


class _Tee(io.TextIOBase):
    """Пишет в прежний поток и в память, не пряча консоль стенда."""

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream
        self._copy = io.StringIO()

    def write(self, text: str) -> int:
        self._copy.write(text)
        return self._stream.write(text)

    def flush(self) -> None:
        self._stream.flush()

    def lines(self) -> list[str]:
        return [line.strip() for line in self._copy.getvalue().splitlines() if line.strip()]


@dataclass(frozen=True)
class _CommandResult:
    """Код CLI и последняя сказанная им причина отказа."""

    code: int
    detail: str


def command_result(command: _Command, args: list[str]) -> _CommandResult:
    """Исполнить команду, одновременно оставив и запомнив stdout/stderr."""
    output, errors = _Tee(sys.stdout), _Tee(sys.stderr)
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
        code = command(args)
    lines = errors.lines() or output.lines()
    return _CommandResult(code, lines[-1] if lines else str(code))
