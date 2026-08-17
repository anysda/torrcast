"""Команда ``cast doctor``: самопроверка окружения по-русски и общий вердикт.
Зовёт её :func:`torrcast.cli.main.main`, сам сценарий живёт в
:mod:`torrcast.usecases.doctor_command`.
"""

from __future__ import annotations

from collections.abc import Callable

from torrcast.usecases.doctor_command import _cmd_doctor


def doctor(command: Callable[[], int] = _cmd_doctor) -> int:
    """``cast doctor`` — терминал, локаль, Prowlarr, TorrServer, ТВ и ffmpeg одним ответом."""
    return command()
