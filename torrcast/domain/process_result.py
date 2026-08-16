"""Completed external-process result used by application scenarios."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProcessResult:
    """Exit status and captured textual streams."""

    returncode: int
    stdout: str = ""
    stderr: str = ""
